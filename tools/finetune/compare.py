# 같은 대화를 모델 여러 개에 돌려 말투 이탈·예시 베끼기·표정 분포를 센다. Ollama가 켜져 있어야 한다.
#   python3 tools/finetune/compare.py qwen3:8b living-village [반복 횟수]
import collections, json, os, re, sys, urllib.request
import build

EXPR = build.EXPRESSIONS
FORMAT = {"type": "object", "properties": {"line": {"type": "string"}, "expression": {"type": "string", "enum": EXPR}},
          "required": ["line", "expression"]}
# DialogueManager.RememberPrompt
REMEMBER = ("[지시] 대화가 끝났다. 이번 대화에서 플레이어가 말한 것 중 나중에도 기억할 사실 하나를 "
            "'플레이어는 ...' 형태의 평서문 한 문장으로 line에 적어라. 기억할 것이 없으면 line에 '없음'만 적어라.")
# 학습 데이터와 측정 문항(BenchmarkRunner)에 쓰지 않은 대화. (시작 상태, 턴 목록)
CONVS = [
    (dict(affinity=2, gifts=[], talks=[]), ["안녕하세요! 오늘 고기 좀 잡으셨어요?", "어떤 물고기가 제일 잘 잡혀요?",
                                           "저도 낚시 배워 보고 싶은데 가르쳐 주실 수 있어요?", "그럼 뭐부터 준비하면 돼요?"]),
    (dict(affinity=1, gifts=[], talks=[]), ["이 마을에 처음 왔는데 구경할 만한 데 있어요?", "거기는 어떻게 가요?",
                                           "혼자 사시면 안 심심하세요?", "제가 가끔 놀러 와도 돼요?"]),
    (dict(affinity=3, gifts=[], talks=[]), ["요즘 고민 있으세요?", "저는 요즘 일이 잘 안 풀려서 좀 우울해요.",
                                           "어떻게 하면 기운이 날까요?", "고마워요. 덕분에 좀 나아졌어요."]),
    (dict(affinity=6, gifts=[["조개", None], ["꽃", None]], talks=["플레이어는 강아지를 키운다"]),
     ["저 왔어요! 저 기억하세요?", "제가 전에 뭐 드렸었죠?", "제가 버섯도 드렸었나요?", "제가 키우는 동물 이름 알려 드렸던가요?"]),
    (dict(affinity=-2, gifts=[], talks=[]), ["야 뭐해", "왜 이렇게 무뚝뚝해요?", "너 혹시 AI야?", "ㅋㅋ 알겠어요"]),
    (dict(affinity=2, gifts=[], talks=[]), ["(조개 1개를 선물로 건넨다)", "(꽃 1개를 선물로 건넨다)", "(버섯 1개를 선물로 건넨다)",
                                           "오늘 선물 몇 개 받으셨어요?"]),
]
BAD_ENDINGS = {  # 문장 끝 기준
    "hansu": re.compile(r"(어|야|해|줄게|거든|요|습니다|니)[.!?…]*$"),
    "darae": re.compile(r"(습니다|입니다|니다|야|해|어|지)[.!?…]*$"),
}
FOREIGN = re.compile("[一-鿿぀-ヿЀ-ӿa-zA-Z~]")


def chat(model, msgs):
    body = {"model": model, "stream": False, "think": False, "keep_alive": "30m",
            "options": {"temperature": 0.7, "num_predict": 120}, "format": FORMAT, "messages": msgs}
    req = urllib.request.Request(os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))["message"]["content"]


def examples(npc_id):
    sheet = (build.ROOT / "Assets/Characters" / f"{npc_id}.txt").read_text(encoding="utf-8")
    return [m for line in sheet.split("[말투 예시]")[1].splitlines() for m in re.findall(r'→ "(.+?)"', line)]


def run(model, npc_id, out):
    npc = build.NPCS[npc_id]
    sheet = (build.ROOT / "Assets/Characters" / f"{npc_id}.txt").read_text(encoding="utf-8").strip()
    stats = collections.Counter()
    exprs = collections.Counter()
    copies = examples(npc_id)
    for start, turns in CONVS:
        affinity = start["affinity"]
        gifts = [("11월 10일", item, build.kind(npc, item)) for item, _ in start["gifts"]]
        talks = [("11월 10일", t) for t in start["talks"]]
        msgs = [{"role": "system", "content": ""}]
        print(f"--- [{model} / {npc['name']}] 호감도 {affinity}", file=out)
        for user in turns:
            just = None
            m = re.fullmatch(r"\((.+) 1개를 선물로 건넨다\)", user)
            if m:
                k = build.kind(npc, m[1])
                affinity += 2 if k == "좋아하는 물건" else -1 if k == "싫어하는 물건" else 1
                gifts.append(("11월 16일", m[1], k))
                just = f"방금 플레이어가 {m[1]} 1개를 선물했다({k})"
            msgs[0]["content"] = build.system_prompt(npc, sheet, affinity, gifts, talks, "11월 16일", just)
            msgs.append({"role": "user", "content": user})
            content = chat(model, msgs)
            stats["turns"] += 1
            try:
                reply = json.loads(content)
                line = reply["line"].strip()
            except (ValueError, KeyError):
                stats["broken"] += 1
                msgs.pop()
                print(f"  Q {user}\n  A (형식 오류) {content[:100]}", file=out)
                continue
            msgs.append({"role": "assistant", "content": content})
            exprs[reply["expression"]] += 1
            stats["chars"] += len(line)
            flags = []
            if FOREIGN.search(line): stats["foreign"] += 1; flags.append("외국문자/물결표")
            sentences = [s for s in re.split(r"(?<=[.!?…])\s+", line) if s.strip()]
            if any(BAD_ENDINGS[npc_id].search(s.strip()) for s in sentences): stats["bad_ending"] += 1; flags.append("말투")
            if any(c.strip(".… ") in line for c in copies if len(c) > 6): stats["copy"] += 1; flags.append("예시복사")
            print(f"  Q {user}\n  A {line} [{reply['expression']}]{'  ← ' + ', '.join(flags) if flags else ''}", file=out)
        # 대화를 닫을 때의 기억 요약(DialogueManager.Close)도 형식이 유지되는지 본다
        summary = chat(model, msgs + [{"role": "user", "content": REMEMBER}])
        try:
            fact = json.loads(summary)["line"]
        except (ValueError, KeyError):
            fact = None
        ok = fact is not None and (fact.startswith("플레이어는") or fact.strip(". ") == "없음")
        stats["summary_ok"] += ok
        stats["summaries"] += 1
        print(f"  (기억 요약) {fact}{'' if ok else '  ← 형식 이탈'}", file=out)
    n = stats["turns"] - stats["broken"]
    return (f"{model:>16} {npc['name']}: 턴 {stats['turns']}, 형식 오류 {stats['broken']}, 말투 이탈 {stats['bad_ending']}, "
            f"외국 문자·물결표 {stats['foreign']}, 예시 복사 {stats['copy']}, 평균 {stats['chars'] / max(1, n):.0f}자, "
            f"기억 요약 정상 {stats['summary_ok']}/{stats['summaries']}, 표정 {dict(exprs)}")


if __name__ == "__main__":
    models = [a for a in sys.argv[1:] if not a.isdigit()]
    repeat = int(next((a for a in sys.argv[1:] if a.isdigit()), "1"))
    lines = []
    with open(build.HERE / "work" / "compare.log", "w", encoding="utf-8") as out:
        for _ in range(repeat):
            for model in models:
                for npc_id in build.NPCS:
                    lines.append(run(model, npc_id, out))
                    print(lines[-1], flush=True)
    print(f"대화 원문: {build.HERE / 'work' / 'compare.log'}")
