# mlx_lm lora를 실행하되, prompt/completion을 채팅 템플릿에 다시 넣지 않고 그대로 토큰화한다.
# build.py가 이미 Ollama와 같은 템플릿으로 조립해 두었기 때문이다. 손실은 completion에만 건다(--mask-prompt).
#   work/.venv/bin/python tools/finetune/train.py --model work/base-4bit --train --data work/data --mask-prompt ...
import sys
from mlx_lm.tuner import datasets
from mlx_lm import lora


def process(self, d):
    prompt = self.tokenizer.encode(d[self.prompt_key], add_special_tokens=False)
    completion = self.tokenizer.encode(d[self.completion_key], add_special_tokens=False)
    return (prompt + completion, len(prompt) if self.mask_prompt else 0)


datasets.CompletionsDataset.process = process

if __name__ == "__main__":
    sys.argv[0] = "mlx_lm.lora"
    lora.main()
