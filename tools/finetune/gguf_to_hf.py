# Ollama가 가진 qwen3:8b(GGUF, Q4_K_M)를 풀어 Hugging Face 형식(bf16 safetensors)으로 저장한다.
# 원본 bf16을 받는 대신 쓴다(네트워크가 느렸다). 게임이 쓰는 것과 같은 가중치에서 출발한다는 장점도 있다.
# config·토크나이저는 Qwen/Qwen3-8B의 작은 파일들을 work/base-bf16에 받아 둔 것을 쓴다.
#   work/.venv/bin/python tools/finetune/gguf_to_hf.py <qwen3:8b GGUF 경로> work/base-bf16 work/base-hf
import json, pathlib, re, shutil, sys
import gguf
import mlx.core as mx
import numpy as np

NAMES = {"token_embd": "model.embed_tokens", "output": "lm_head", "output_norm": "model.norm"}
BLOCK = {"attn_q": "self_attn.q_proj", "attn_k": "self_attn.k_proj", "attn_v": "self_attn.v_proj",
         "attn_output": "self_attn.o_proj", "attn_q_norm": "self_attn.q_norm", "attn_k_norm": "self_attn.k_norm",
         "attn_norm": "input_layernorm", "ffn_norm": "post_attention_layernorm",
         "ffn_gate": "mlp.gate_proj", "ffn_up": "mlp.up_proj", "ffn_down": "mlp.down_proj"}


def hf_name(name):
    base, suffix = name.rsplit(".", 1)
    m = re.fullmatch(r"blk\.(\d+)\.(\w+)", base)
    return (f"model.layers.{m[1]}.{BLOCK[m[2]]}" if m else NAMES[base]) + "." + suffix


def main(src, meta_dir, out):
    out.mkdir(parents=True, exist_ok=True)
    for f in meta_dir.iterdir():
        if f.is_file() and f.name != "model.safetensors.index.json":
            shutil.copy(f, out / f.name)

    reader = gguf.GGUFReader(src)
    config = json.loads((out / "config.json").read_text())
    expected = 3 + config["num_hidden_layers"] * len(BLOCK)
    assert len(reader.tensors) == expected, (len(reader.tensors), expected)

    index, shard, size = {}, {}, 0
    def flush():
        name = f"model-{len(set(index.values())) + 1:05d}.safetensors"
        mx.save_safetensors(str(out / name), shard, metadata={"format": "mlx"})
        index.update({k: name for k in shard})

    for t in reader.tensors:
        shape = tuple(int(d) for d in reversed(t.shape))  # GGUF는 [열, 행] 순서
        w = gguf.quants.dequantize(t.data, t.tensor_type).reshape(shape).astype(np.float32)
        shard[hf_name(t.name)] = mx.array(w).astype(mx.bfloat16)
        size += w.size * 2
        if size > 4 << 30:
            flush()
            shard, size = {}, 0
    if shard:
        flush()
    (out / "model.safetensors.index.json").write_text(json.dumps({"metadata": {}, "weight_map": index}, indent=2))
    print(f"{len(index)} tensors → {out}")


if __name__ == "__main__":
    main(sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))
