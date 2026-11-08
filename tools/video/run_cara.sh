#!/bin/bash
# Tanda del 08/11: la «cara que aparece de la nada» al final del video largo (V10, encadenado por ultimo fotograma).
# Todo seguido, sin intervencion; ~30 min en una 5090. Se lanza en segundo plano:
#   nohup bash run_cara.sh > /workspace/_claude/video/run_cara.out 2>&1 &
# Variantes (mismo seed 42+i por tramo):
#   k0 control: prompts del 07/11 + CLIP del ultimo fotograma (= l3 del 07/11)
#   k1 prompts del 07/11 + CLIP de la imagen ORIGINAL
#   k2 prompts NUEVOS (regla «solo los que se ven») + CLIP del ultimo fotograma
#   k3 prompts nuevos + CLIP original
#   k4 k3 con tramos cortos: 5 x 49 fotogramas (~10 s igual)
#   k5 k3 + refinado del ultimo fotograma con Krea 2 + LoRA del personaje (denoise 0,25)
#   k6 k3 con la imagen del taller (FreeFuse, 3 personajes)
set -u
H=$(cd "$(dirname "$0")" && pwd)
W=/workspace/_claude/video; mkdir -p $W/cara
E=/workspace/_inventario_20261031/entrada.png
F=/workspace/outputs/comfy/freefuse_libre/frypex_ceyblan_ahatly_00587_.png
[ -f "$F" ] || F=$(ls -t /workspace/outputs/comfy/freefuse_libre/*.png 2>/dev/null | head -1)
VIEJO=$W/prueba_a/125443_receta_entrada_s3.json
echo "== prompts nuevos"; date +%T
python3 $H/prompts.py $E --out $W/cara/p_entrada.json --seg 3 --int intensa --seed 1
python3 $H/prompts.py $F --out $W/cara/p_taller.json --seg 3 --int intensa --seed 1
echo "== videos"; date +%T
python3 $H/largo.py $VIEJO --imagen $E --tag k0_control
python3 $H/largo.py $VIEJO --imagen $E --tag k1_clip_original --clip original
python3 $H/largo.py $W/cara/p_entrada.json --tag k2_prompt_nuevo
python3 $H/largo.py $W/cara/p_entrada.json --tag k3_nuevo_clip_original --clip original
python3 $H/largo.py $W/cara/p_entrada.json --tag k4_tramos_cortos --clip original --frames 49 --tramos 5
python3 $H/largo.py $W/cara/p_entrada.json --tag k5_refinado_krea --clip original --refinar 0.25
python3 $H/largo.py $W/cara/p_taller.json --tag k6_taller --clip original --w 768 --h 576
echo "== coser y audio"; date +%T
for t in k0_control k1_clip_original; do python3 $H/coser.py $t 1 $W/cara/p_entrada.json; done
for t in k2_prompt_nuevo k3_nuevo_clip_original k4_tramos_cortos k5_refinado_krea; do python3 $H/coser.py $t 1 $W/cara/p_entrada.json; done
python3 $H/coser.py k6_taller 1 $W/cara/p_taller.json
echo "== metricas y visor"; date +%T
python3 $H/metricas.py > $W/cara/metricas.txt
python3 $H/visor.py $H/tarjetas_cara.json --nombre visor_cara.html
python3 $H/wf.py --dest /workspace/outputs/comfy/video_pruebas_20261108/_wf
mkdir -p /workspace/outputs/comfy/video_pruebas_20261108/_scripts && cp -r $W/cara $W/largo.log /workspace/outputs/comfy/video_pruebas_20261108/_scripts/ 2>/dev/null
echo FIN_CARA; date +%T
