# -*- coding: utf-8 -*-
"""
rafa_prompt_studio_freefuse.py — Prompt Studio FreeFuse + Spans FreeFuse
Parte del repo comfyui-rafa-nodes - github.com/osuvense/comfyui-rafa-nodes

Para apilar personajes con FreeFuse (https://github.com/yaoliliu/FreeFuse) en la
misma imagen. Prompt Studio normal queda intacto para los workflows sin FreeFuse;
este nodo comparte con el todo el codigo de perfiles, aperturas y validacion.

Por que un nodo aparte y no un interruptor: en ComfyUI las salidas de un nodo son
fijas (tambien en el esquema V3: lo dinamico son las entradas), y este necesita
una salida mas y otro contrato con Claude.

FreeFuse asigna cada LoRA a una region de la imagen a partir de un trozo de texto
(span) que tiene que aparecer LITERAL en el prompt, mas una frase de fondo, tambien
literal. Si el fondo va vacio, en Krea 2 no hay canal de fondo y las mascaras de
los personajes se reparten la imagen entera. Para que los spans sean limpios, el
codigo monta el prompt siempre en el mismo orden:

    <entorno + personas sin LoRA>. <P1 entero>. <P2 entero>. ... <acabado>

- Cada personaje aparece una sola vez por su trigger y todo lo suyo (posicion,
  pose, ropa, accion) va seguido detras de su apertura.
- Dentro del bloque de uno, a los demas se les nombra sin trigger ni class.
- El entorno no nombra a ningun personaje con LoRA.

Como el orden es fijo, los spans se pueden recalcular desde el prompt final aunque
se haya editado en PromptApprovalGate: lo hace el nodo «Spans FreeFuse (Rafa)»,
que va DETRAS de la puerta y cuyas salidas se cablean a FreeFuseConceptMap
(concept_text_1..4 y background_text). Prompt Studio FreeFuse le pasa la lista de
triggers y el acabado por la salida 'freefuse_info'.
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Tuple

try:
    from . import rafa_prompt_studio as rps
except ImportError:  # tests y uso fuera de paquete
    import rafa_prompt_studio as rps


LOG = "[RafaPromptStudioFF]"
MAX_FF = 4  # FreeFuseConceptMap admite 4 sujetos
NINGUNO = rps.NINGUNO


def adapter_de(choice: str) -> str:
    """Nombre de adapter de FreeFuse para un personaje: 'txr_' + id (+ variante).
    El prefijo txr_ activa el parche local de texto de FreeFuse (freefuse/_SIGUIENTE.md)."""
    pid, _, var = str(choice).partition("/")
    return "txr_" + re.sub(r"[^a-z0-9]+", "_", (pid + ("_" + var if var else "")).lower()).strip("_")


def leer_reparto(reparto: str) -> List[str]:
    """Lista de personajes (choices de perfil) desde la salida 'reparto' del nodo Reparto."""
    if not str(reparto or "").strip():
        return []
    try:
        data = json.loads(reparto)
    except Exception as e:
        raise ValueError(f"reparto no es JSON ({e}): conéctalo a Reparto FreeFuse (Rafa).")
    return [str(x.get("personaje")) for x in data if isinstance(x, dict) and x.get("personaje")]


FF_RULES = """FREEFUSE MODE (this block OVERRIDES the marker rules above).
In this image each character's LoRA is applied only to the region of the image that matches his own text span, so the code assembles the prompt from separate pieces, always in this order:
  <setting>. <P1 opening>, <P1 block>. <P2 opening>, <P2 block>. ... <finish>
Do NOT write a single paragraph and do NOT use markers anywhere. Return the pieces:

- "setting": one or two sentences that OPEN the prompt: the place and background, props of the place, the light and atmosphere, and every person WITHOUT a LoRA (described plainly, e.g. "several other naked men watching from the benches"). It never mentions any character with a LoRA: no names, no markers, no "three men", no "the couple". Write it as a scene description, e.g. "Inside a steamy wooden sauna with tiered benches and warm amber light".
- "subjects": an object with one block per character, keys "P1", "P2"... Each block is placed right after that character's opening, which the code writes ("Alfa, a heavyset older man, with ..., "), so it must read as the continuation of that appositive: "sitting at the left of the frame on the lower bench, legs apart, a white towel over one shoulder, ...". Put EVERYTHING that belongs to that character in his block, as one continuous description: his zone of the frame, pose and limbs, clothing or nudity, props, what he does and to whom.
  * When he interacts with another character, refer to that one WITHOUT name, marker or class word, by position or role: "the man at the right of the frame", "the man kneeling in front of him".
  * Never write any character's name, trigger, marker or class word inside another character's block, nor in the setting or the finish.
  * Give each character his own clear zone of the frame (left / centre / right, foreground / background) and keep interactions readable; prefer poses where the bodies stay distinguishable.
  * Still do NOT describe invariant traits (build, face, hair, mustache, body hair, skin, eyes, feet, genitals size): the LoRA and the opening give them. Describe only what varies.
- "finish": the photographic finish only (camera, lens, light quality, image character), shared by everyone, with no people in it.

OUTPUT FORMAT: reply ONLY with valid JSON, no text before or after, no markdown fences."""


def output_format_ff(n_pers: int, negative: bool, con_estados: bool) -> str:
    keys = ", ".join(f'"P{i}": "..."' for i in range(1, n_pers + 1)) or ""
    estados = ('\n  "states": {"P1": []},  (optional state ids per character; empty unless the user asks for them)'
               if con_estados else "")
    neg = ('"negative": "negative prompt in English (the target model uses one)"'
           if negative else '"negative": ""  (this model does not use a negative prompt: leave it empty)')
    return f"""JSON keys, exactly:
{{
  "setting": "...",
  "subjects": {{{keys}}},
  "finish": "...",
  {neg},{estados}
  "razonamiento": "brief explanation in Spanish of your choices"
}}"""


def build_variable_ff(nsfw: str, encuadre: str, estilo: str, negative: bool, n_pers: int,
                      extra: str, con_estados: bool) -> str:
    estilo_txt = {
        "caption": ("STYLE: caption. Each character's block is long and detailed, like his training captions; "
                    "the setting is rich; the finish follows the characters' caption format."),
        "compacto": "STYLE: compact. Short setting (one sentence), short blocks (one clause each), short finish.",
    }[estilo]
    lines = [
        f"NSFW LEVEL: {nsfw}." + (" Sexual content explicit and named." if nsfw == "explicit" else
                                  " Nudity or tension without explicit sex acts." if nsfw == "suggestive" else
                                  " No nudity, no sexual content."),
        f"FRAMING: {encuadre}." + (" Choose what suits the scene." if encuadre == "auto" else ""),
        estilo_txt,
        (f"CHARACTERS IN THIS IMAGE: {n_pers} (blocks P1..P{n_pers}, all required)." if n_pers else
         "NO CHARACTERS WITH A LoRA: put every person in the setting and leave \"subjects\" empty."),
    ]
    if extra.strip():
        lines.append("EXTRA INSTRUCTIONS FROM RAFA (take priority over defaults):\n" + extra.strip())
    lines.append(output_format_ff(n_pers, negative, con_estados))
    return "\n\n".join(lines)


def _limpia(t: str) -> str:
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t.strip(" ,;")


def _sin_punto(t: str) -> str:
    return _limpia(t).rstrip(".").rstrip()


def _menciones(text: str, p: Dict[str, Any]) -> List[str]:
    """Trigger, class (y frases reservadas) de p que aparecen en text."""
    out = []
    if re.search(r"\b" + re.escape(p["trigger"]) + r"\b", text):
        out.append(p["trigger"])
    for r in p["reservado"]:
        if r and re.search(r"\b" + re.escape(r) + r"\b", text, re.I):
            out.append(r)
    return out


def montar_ff(data: Dict[str, Any], pers: List[Dict[str, Any]], estilo: str) -> Tuple[str, List[str], List[str]]:
    """Devuelve (prompt, problemas_para_reintento, avisos)."""
    problemas: List[str] = []
    avisos: List[str] = []
    setting = _sin_punto(data.get("setting"))
    subj = data.get("subjects") if isinstance(data.get("subjects"), dict) else {}
    finish = _limpia(data.get("finish"))

    if rps._MARKER_RE.search(setting + " " + finish) or any(
            rps._MARKER_RE.search(str(v or "")) for v in subj.values()):
        problemas.append("markers like [P1] are not allowed in FreeFuse mode")
    if not setting:
        problemas.append("the setting is empty (FreeFuse needs it as the background span)")
    for p in pers:
        m = _menciones(setting, p) + _menciones(finish, p)
        if m:
            problemas.append(f"the setting/finish mentions a character ({', '.join(m)})")

    bloques = []
    for i, p in enumerate(pers, 1):
        txt = _sin_punto(subj.get(f"P{i}"))
        if not txt:
            problemas.append(f"block P{i} is missing")
            continue
        for j, q in enumerate(pers, 1):
            m = _menciones(txt, q)
            if not m:
                continue
            if j != i:
                problemas.append(f"block P{i} mentions another character by name or class ({', '.join(m)}); "
                                 f"refer to him by position or role")
            else:
                problemas.append(f"block P{i} repeats his own name, class word or reserved phrase "
                                 f"({', '.join(m)}); the code writes the opening")
        bloques.append(rps.apertura(p) + ", " + txt + ".")

    partes = ([setting + "."] if setting else []) + bloques + ([finish] if finish else [])
    prompt = " ".join(partes)
    prompt = rps.cerrar_acabado(prompt, pers, estilo)
    for p in pers:
        n = len(re.findall(r"\b" + re.escape(p["trigger"]) + r"\b", prompt))
        if n != 1:
            avisos.append(f"{p['trigger']} aparece {n} veces en el prompt (FreeFuse necesita 1).")
    return prompt, problemas, avisos


def calcular_spans(prompt: str, triggers: List[str], finish: str = "") -> Dict[str, Any]:
    """Spans y fondo literales a partir del prompt final (editado o no).
    Bloque de cada personaje: de su trigger al siguiente trigger, o al acabado."""
    text = prompt or ""
    pos = []
    faltan = []
    for i, t in enumerate(triggers):
        m = re.search(r"\b" + re.escape(t) + r"\b", text)
        if m:
            pos.append((m.start(), i))
        else:
            faltan.append(t)
    if faltan:
        raise ValueError("Spans FreeFuse: no encuentro en el prompt el trigger de " + ", ".join(faltan)
                         + ". Si lo has quitado al editar, FreeFuse no puede asignar su LoRA.")
    pos.sort()
    fin_total = len(text)
    fpos = text.rfind(finish) if finish else -1
    if fpos > pos[-1][0]:
        fin_total = fpos
    spans = [""] * len(triggers)
    avisos = []
    for k, (start, i) in enumerate(pos):
        end = pos[k + 1][0] if k + 1 < len(pos) else fin_total
        span = text[start:end].rstrip(" ,.;:\n\t")
        spans[i] = span
    fondo = text[:pos[0][0]].strip().rstrip(" ,.;:")
    if not fondo:
        avisos.append("Fondo vacio: no hay texto antes del primer personaje. En Krea 2 el fondo queda al 0 % "
                      "y las mascaras se reparten la imagen entera.")
    for t in triggers:
        if len(re.findall(r"\b" + re.escape(t) + r"\b", text)) > 1:
            avisos.append(f"{t} aparece mas de una vez; el span va de su primera mencion al siguiente personaje.")
    if fpos < 0 and finish:
        avisos.append("No encuentro el acabado original: el ultimo span llega hasta el final del prompt.")
    return {"spans": spans, "fondo": fondo, "avisos": avisos}


class RafaPromptStudioFreeFuse(rps.RafaPromptStudio):
    """Prompt Studio para FreeFuse: hasta 4 personajes, prompt montado por bloques."""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        base = super().INPUT_TYPES()
        req = dict(base["required"])
        req.pop("variantes", None)
        pers = req["personaje_3"]
        nuevo = {}
        for k, v in req.items():
            nuevo[k] = v
            if k == "personaje_3":
                nuevo["personaje_4"] = pers
        nuevo["escena"] = ("STRING", {"multiline": True, "default": "",
                                      "tooltip": "La escena. Los personajes elegidos abajo son P1-P4, de "
                                                 "izquierda a derecha si no dices otra cosa."})
        opt = dict(base["optional"])
        opt["reparto"] = ("STRING", {"forceInput": True,
                                     "tooltip": "Salida 'reparto' de Reparto FreeFuse: si está conectada, "
                                                "manda sobre personaje_1-4."})
        return {"required": nuevo, "optional": opt}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "negative", "razonamiento", "freefuse_info")
    FUNCTION = "generar_ff"
    CATEGORY = "rafa"

    @classmethod
    def IS_CHANGED(cls, escena="", base="", lexico=NINGUNO, personaje_1=NINGUNO, personaje_2=NINGUNO,
                   personaje_3=NINGUNO, personaje_4=NINGUNO, usar_estetica=True, nsfw="", encuadre="",
                   estilo="", creatividad=0.8, seed=0, modelo_claude="", extra="", **kwargs):
        key = repr(("ff1", escena, base, lexico, personaje_1, personaje_2, personaje_3, personaje_4,
                    bool(usar_estetica), nsfw, encuadre, estilo, round(float(creatividad), 4), int(seed),
                    modelo_claude, extra, bool(kwargs.get("nombrar_rasgos_fijos", True)), str(kwargs.get("reparto") or ""),
                    cls._profiles_fingerprint(base, lexico, (personaje_1, personaje_2, personaje_3, personaje_4),
                                              bool(usar_estetica))))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @classmethod
    def preparar_ff(cls, base, lexico, personajes_sel, usar_estetica, nsfw, encuadre, estilo, extra,
                    nombrar_fijos=True) -> Dict[str, Any]:
        prep = cls.preparar(base, lexico, personajes_sel, usar_estetica, nsfw, encuadre, estilo, 1,
                            extra, nombrar_fijos)
        pers = prep["personajes"]
        if len(pers) > MAX_FF:
            raise ValueError(f"FreeFuse admite como mucho {MAX_FF} personajes.")
        prep["stable"] = prep["stable"] + "\n\n" + "=" * 50 + "\n\n" + FF_RULES
        prep["variable"] = build_variable_ff(nsfw, encuadre, estilo, prep["negative_ok"], len(pers),
                                             extra or "", any(p["estados"] for p in pers))
        return prep

    @staticmethod
    def postprocesar_ff(data: Dict[str, Any], prep: Dict[str, Any], estilo: str) -> Dict[str, Any]:
        pers = [dict(p) for p in prep["personajes"]]
        avisos = []
        est = data.get("states") if isinstance(data.get("states"), dict) else {}
        for i, p in enumerate(pers, 1):
            ids = est.get(f"P{i}") or []
            ids = [str(x) for x in ids] if isinstance(ids, list) else []
            validos = {e["id"] for e in p["estados"]}
            avisos += [f"{p['trigger']}: estado «{x}» no existe en su perfil; se ignora." for x in ids
                       if x not in validos]
            p["pedidos"] = [x for x in ids if x in validos]
        prompt, problemas, av = montar_ff(data, pers, estilo)
        avisos += av + rps.validar(prompt, pers)
        negative = str(data.get("negative") or "").strip() if prep["negative_ok"] else ""
        info = {"triggers": [p["trigger"] for p in pers], "adapters": [adapter_de(p["choice"]) for p in pers],
                "finish": _limpia(data.get("finish"))}
        return {"prompt": prompt, "negative": negative, "problemas": problemas, "avisos": avisos,
                "bloqueados": rps.terminos_bloqueados(prompt + " " + negative),
                "razonamiento": str(data.get("razonamiento") or "").strip(), "info": info}

    def generar_ff(self, escena, base, lexico, personaje_1, personaje_2, personaje_3, personaje_4,
                   usar_estetica, nsfw, encuadre, estilo, creatividad, seed, api_key="",
                   modelo_claude="claude-sonnet-4-6", extra="", nombrar_rasgos_fijos=True, reparto=""):
        import os
        # Valores de los widgets tal cual (el reparto los sobreescribe abajo): son los que guarda el grafo del PNG
        _widgets = dict(personaje_1=personaje_1, personaje_2=personaje_2, personaje_3=personaje_3,
                        personaje_4=personaje_4)
        sel = leer_reparto(reparto)
        if sel:
            sel = sel + [NINGUNO] * (MAX_FF - len(sel))
            personaje_1, personaje_2, personaje_3, personaje_4 = sel[:MAX_FF]
        if not str(escena).strip():
            raise ValueError("La escena no puede estar vacia")
        if rps.anthropic is None:
            raise RuntimeError("Falta el SDK anthropic (requirements.txt del repo)")
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("No hay API key: ANTHROPIC_API_KEY o el input api_key.")
        prep = self.preparar_ff(base, lexico, (personaje_1, personaje_2, personaje_3, personaje_4),
                                bool(usar_estetica), nsfw, encuadre, estilo, extra, bool(nombrar_rasgos_fijos))
        client = rps.anthropic.Anthropic(api_key=key)
        model = (modelo_claude or "").strip() or "claude-sonnet-4-6"
        messages = [{"role": "user", "content": str(escena)}]
        res = None
        for intento in (1, 2):
            api_kwargs = dict(
                model=model, max_tokens=4096,
                temperature=max(0.0, min(1.0, float(creatividad))),
                system=[{"type": "text", "text": prep["stable"], "cache_control": {"type": "ephemeral"}},
                        {"type": "text", "text": prep["variable"]}],
                messages=messages)
            try:
                msg = rps.create_with_fallback(client, api_kwargs)
            except Exception as e:
                raise RuntimeError(f"Error de la API: {e}")
            raw = rps.extract_text(msg)
            u = getattr(msg, "usage", None)
            if u is not None:
                print(f"{LOG} base={base} seed={seed} intento={intento} in:{u.input_tokens} "
                      f"out:{u.output_tokens} cache_w:{getattr(u, 'cache_creation_input_tokens', 0) or 0} "
                      f"cache_r:{getattr(u, 'cache_read_input_tokens', 0) or 0}")
            try:
                data = rps.parse_json(raw)
            except Exception as e:
                if intento == 1:
                    print(f"{LOG} reintento: JSON invalido ({e})")
                    messages = messages + [{"role": "assistant", "content": raw},
                                           {"role": "user", "content": "That was not valid JSON. Reply again "
                                            "with ONLY the JSON object, nothing else."}]
                    continue
                raise RuntimeError(f"La respuesta no es JSON valido ({e}): {raw[:300]}")
            res = self.postprocesar_ff(data, prep, estilo)
            if not res["bloqueados"] and not res["problemas"]:
                break
            if intento == 1:
                problemas = list(res["problemas"])
                if res["bloqueados"]:
                    problemas.insert(0, "it contains forbidden terms: " + ", ".join(res["bloqueados"]))
                print(f"{LOG} reintento: {'; '.join(problemas)}")
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Rewrite the JSON fixing this: " + "; ".join(problemas)
                     + ". Every person is an adult man. Keep everything else."}]
        if res is None:
            raise RuntimeError("Sin respuesta valida de la API.")
        if res["bloqueados"]:
            raise RuntimeError("Prompt bloqueado (regla del project): contiene "
                               + ", ".join(res["bloqueados"]) + ". No se emite.")
        avisos = prep["avisos"] + [f"Sin corregir tras el reintento: {p}" for p in res["problemas"]] + res["avisos"]
        partes = []
        if avisos:
            partes.append("AVISOS:\n" + "\n".join("- " + a for a in avisos))
        if res["razonamiento"]:
            partes.append(res["razonamiento"])
        sp = calcular_spans(res["prompt"], res["info"]["triggers"], res["info"]["finish"])
        partes.append("SPANS (si no editas el prompt):\n" + "\n".join(
            f"[{i + 1}] {s}" for i, s in enumerate(sp["spans"])) + f"\n[fondo] {sp['fondo']}")
        for a in avisos:
            print(f"{LOG} AVISO: {a}")
        rps._registrar_receta("RafaPromptStudioFreeFuse", dict(
            escena=escena, base=base, lexico=lexico, **_widgets, usar_estetica=usar_estetica, nsfw=nsfw,
            encuadre=encuadre, estilo=estilo, creatividad=creatividad, seed=seed, modelo_claude=modelo_claude,
            extra=extra, nombrar_rasgos_fijos=nombrar_rasgos_fijos, reparto=reparto,
            personajes_reparto=[p for p in (personaje_1, personaje_2, personaje_3, personaje_4) if p != NINGUNO]),
            res["prompt"], res["negative"])
        return (res["prompt"], res["negative"], "\n\n----\n\n".join(partes),
                json.dumps(res["info"], ensure_ascii=False))


class RafaFreeFuseSpans:
    """Recalcula spans y fondo desde el prompt final (despues de PromptApprovalGate)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt": ("STRING", {"forceInput": True, "tooltip": "El prompt que va al encoder (el aprobado)."}),
            "freefuse_info": ("STRING", {"forceInput": True, "tooltip": "Salida freefuse_info de Prompt Studio FreeFuse."}),
        }}

    # Las salidas 7-10 (adapter_N) se añadieron despues: van al final para no descuadrar workflows.
    RETURN_TYPES = ("STRING",) * 11
    RETURN_NAMES = ("prompt", "span_1", "span_2", "span_3", "span_4", "fondo", "informe",
                    "adapter_1", "adapter_2", "adapter_3", "adapter_4")
    FUNCTION = "spans"
    CATEGORY = "rafa"

    def spans(self, prompt, freefuse_info):
        try:
            info = json.loads(freefuse_info or "{}")
        except Exception as e:
            raise ValueError(f"freefuse_info no es JSON ({e}): conectalo a Prompt Studio FreeFuse.")
        trig = [str(t) for t in info.get("triggers") or []]
        r = calcular_spans(prompt, trig, str(info.get("finish") or ""))
        s = r["spans"] + [""] * (MAX_FF - len(r["spans"]))
        informe = "\n".join([f"[{i + 1}] {x}" for i, x in enumerate(s) if x] + [f"[fondo] {r['fondo']}"]
                            + (["", "AVISOS:"] + ["- " + a for a in r["avisos"]] if r["avisos"] else []))
        for a in r["avisos"]:
            print(f"{LOG} AVISO spans: {a}")
        ad = [str(a) for a in info.get("adapters") or []]
        ad = ad + [""] * (MAX_FF - len(ad))
        return (prompt, s[0], s[1], s[2], s[3], r["fondo"], informe, ad[0], ad[1], ad[2], ad[3])


def _lista_loras() -> List[str]:
    try:
        import folder_paths
        return [NINGUNO] + list(folder_paths.get_filename_list("loras"))
    except Exception:
        return [NINGUNO]


def plan_reparto(slots: List[Tuple[str, str, float]]) -> List[Dict[str, Any]]:
    """slots = [(personaje, lora, fuerza)] x4 -> los activos, en orden (huecos compactados)."""
    activos = []
    for i, (pers, lora, fuerza) in enumerate(slots, 1):
        if not pers or pers == NINGUNO:
            if lora and lora != NINGUNO:
                raise ValueError(f"Reparto: el hueco {i} tiene LoRA pero no personaje.")
            continue
        if not lora or lora == NINGUNO:
            raise ValueError(f"Reparto: {pers} (hueco {i}) no tiene LoRA elegido.")
        activos.append({"personaje": pers, "lora": lora, "fuerza": float(fuerza), "adapter": adapter_de(pers)})
    vistos = set()
    for a in activos:
        if a["adapter"] in vistos:
            raise ValueError(f"Reparto: {a['personaje']} está dos veces.")
        vistos.add(a["adapter"])
    if not activos:
        raise ValueError("Reparto: elige al menos un personaje.")
    return activos


class RafaRepartoFreeFuse:
    """Un solo sitio para elegir a los personajes: carga sus LoRAs con FreeFuseLoRALoader
    (adapter txr_<id>, mismo orden) y saca 'reparto' para Prompt Studio FreeFuse e Ideas.
    'ninguno' en un hueco = ese personaje no entra."""

    @classmethod
    def INPUT_TYPES(cls):
        pers = rps.personaje_options()
        loras = _lista_loras()
        req = {"model": ("MODEL",), "clip": ("CLIP",)}
        for i in range(1, MAX_FF + 1):
            req[f"personaje_{i}"] = (pers, {"default": NINGUNO})
            req[f"lora_{i}"] = (loras, {"default": NINGUNO})
            req[f"fuerza_{i}"] = ("FLOAT", {"default": 1.0, "min": -2.0, "max": 3.0, "step": 0.05})
        return {"required": req}

    RETURN_TYPES = ("MODEL", "CLIP", "FREEFUSE_DATA", "STRING")
    RETURN_NAMES = ("model", "clip", "freefuse_data", "reparto")
    FUNCTION = "cargar"
    CATEGORY = "rafa"

    def cargar(self, model, clip, **kw):
        slots = [(kw.get(f"personaje_{i}"), kw.get(f"lora_{i}"), kw.get(f"fuerza_{i}", 1.0))
                 for i in range(1, MAX_FF + 1)]
        activos = plan_reparto(slots)
        try:
            import nodes as comfy_nodes
            Loader = comfy_nodes.NODE_CLASS_MAPPINGS["FreeFuseLoRALoader"]
        except Exception:
            raise RuntimeError("Reparto: no encuentro FreeFuseLoRALoader. ¿Está instalado freefuse_comfyui?")
        ffdata = None
        for a in activos:
            model, clip, ffdata = Loader().load_lora(model, clip, a["lora"], a["adapter"], a["fuerza"], 0.0,
                                                     ffdata)
            print(f"{LOG} reparto: {a['personaje']} -> {a['lora']} a {a['fuerza']} ({a['adapter']})")
        reparto = json.dumps([{"personaje": a["personaje"], "adapter": a["adapter"]} for a in activos],
                             ensure_ascii=False)
        return (model, clip, ffdata, reparto)


NODE_CLASS_MAPPINGS = {"RafaPromptStudioFreeFuse": RafaPromptStudioFreeFuse,
                       "RafaFreeFuseSpans": RafaFreeFuseSpans,
                       "RafaRepartoFreeFuse": RafaRepartoFreeFuse}
NODE_DISPLAY_NAME_MAPPINGS = {"RafaPromptStudioFreeFuse": "Prompt Studio FreeFuse (Rafa)",
                              "RafaFreeFuseSpans": "Spans FreeFuse (Rafa)",
                              "RafaRepartoFreeFuse": "Reparto FreeFuse (Rafa)"}
