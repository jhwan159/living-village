# 원본 qwen3:8b GGUF를 복사하면서 LoRA로 바뀐 텐서만 합친 모델(work/fused) 값으로 바꾼다.
# 바뀌지 않은 텐서는 원본 Q4_K_M 그대로다. 바뀐 텐서는 Q8_0으로 쓴다(gguf-py가 Q4_K/Q6_K 양자화를 못 한다).
# Ollama가 safetensors로 만든 모델은 MLX 엔진에서 돌고, Homebrew판에는 구조화 출력(format)이 없어 게임에서 쓸 수 없다.
#   work/.venv/bin/python tools/finetune/merge_gguf.py <qwen3:8b GGUF> work/base-hf work/fused work/living-village.gguf
import json, sys
import gguf
import mlx.core as mx
import numpy as np
from gguf import GGMLQuantizationType as T
from gguf_to_hf import hf_name

src, base_dir, fused_dir, out = sys.argv[1:5]


def loader(d):
    index = json.load(open(f"{d}/model.safetensors.index.json"))["weight_map"]
    cache = {}
    def get(name):
        f = index[name]
        if f not in cache:
            cache.clear()
            cache[f] = mx.load(f"{d}/{f}")
        return cache[f][name]
    return get


base, fused = loader(base_dir), loader(fused_dir)
reader = gguf.GGUFReader(src)
arch = bytes(reader.fields["general.architecture"].parts[-1]).decode()
writer = gguf.GGUFWriter(out, arch=arch, endianess=reader.endianess)

for field in reader.fields.values():  # gguf_new_metadata.copy_with_new_metadata와 같은 방식
    if field.name == gguf.Keys.General.ARCHITECTURE or field.name.startswith("GGUF."):
        continue
    val_type = field.types[0]
    sub_type = field.types[-1] if val_type == gguf.GGUFValueType.ARRAY else None
    writer.add_key_value(field.name, field.contents(), val_type, sub_type=sub_type)

tensors, changed = [], 0
for t in reader.tensors:
    name = hf_name(t.name)
    data, qtype = t.data, t.tensor_type
    if t.tensor_type not in (T.F32,):  # 정규화 가중치(F32)는 LoRA 대상이 아니다
        new = fused(name)
        if mx.any(new != base(name)).item():
            w = np.array(new.astype(mx.float32))
            qtype = T.F16 if t.tensor_type == T.F16 else T.Q8_0
            data = gguf.quants.quantize(w, qtype)
            changed += 1
    tensors.append((t.name, data, qtype))
    writer.add_tensor_info(t.name, data.shape, data.dtype, data.nbytes, raw_dtype=qtype)

writer.write_header_to_file()
writer.write_kv_data_to_file()
writer.write_ti_data_to_file()
for _, data, _ in tensors:
    writer.write_tensor_data(data, tensor_endianess=reader.endianess)
writer.close()
print(f"바뀐 텐서 {changed}개 → {out}")
