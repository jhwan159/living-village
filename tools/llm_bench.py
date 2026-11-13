"""Ollama 대사 응답 시간 측정. 사용: python3 llm_bench.py [모델] [횟수] [서버주소]"""
import json, statistics, sys, time, urllib.request

model = sys.argv[1] if len(sys.argv) > 1 else "qwen3:8b"
runs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
host = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:11434"

EXPRESSIONS = ["neutral", "happy", "sad", "angry", "surprised"]
SYSTEM = """너는 마을 주민 '한수'다. 말투: 무뚝뚝한 반말, 짧게 말한다. 관심사: 낚시, 바다 날씨.
알고 있는 사실: 마을 동쪽 부두에서 30년째 어부로 일한다.
[기억] (여기 적힌 것만 실제로 있었던 일이다. 없는 일은 지어내지 마라.)
- 어제 플레이어에게 조개를 선물받았다(좋아함).
[현재 상황] 장소: 부두, 호감도: 보통, 방금 일어난 일: 없음
규칙: 한국어로 1~2문장만 말한다. JSON으로만 답한다."""
QUESTIONS = ["안녕하세요!", "요즘 뭐 하고 지내세요?", "제가 어제 뭐 드렸는지 기억나요?",
             "제가 드린 꽃은 마음에 들었어요?", "오늘 날씨 어때요?"]


def ask(question):
    body = {
        "model": model, "stream": False, "think": False, "keep_alive": "30m",
        "options": {"temperature": 0.7, "num_predict": 120},
        "format": {"type": "object",
                   "properties": {"line": {"type": "string"},
                                  "expression": {"type": "string", "enum": EXPRESSIONS}},
                   "required": ["line", "expression"]},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
    }
    req = urllib.request.Request(host + "/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as res:
        content = json.load(res)["message"]["content"]
    return time.perf_counter() - start, content


ask("안녕")  # 모델 로딩 시간은 측정에서 제외
times, bad = [], 0
for i in range(runs):
    q = QUESTIONS[i % len(QUESTIONS)]
    sec, content = ask(q)
    times.append(sec)
    try:
        out = json.loads(content)
        assert out["line"].strip() and out["expression"] in EXPRESSIONS
        print(f"{sec:5.2f}s [{out['expression']}] {q} -> {out['line']}")
    except (ValueError, KeyError, AssertionError):
        bad += 1
        print(f"{sec:5.2f}s 형식 오류: {content!r}")

times.sort()
print(f"\n{model}: 중앙값 {statistics.median(times):.2f}s, 최대 {times[-1]:.2f}s, 형식 오류 {bad}/{runs}")
