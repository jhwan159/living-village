# data/*.jsonl 대화를 게임이 실제로 보내는 프롬프트로 바꿔 work/data/{train,valid}.jsonl을 만든다.
# 시스템 프롬프트는 Npc.SystemPrompt, 선물 처리는 GameState.Gift, 턴 이력은 DialogueManager.Ask와 같다.
# 문자열은 qwen3:8b의 Ollama 템플릿(think=false)이 만드는 것과 같게 직접 조립한다.
#   python3 tools/finetune/build.py
import json, random, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "work" / "data"
EXPRESSIONS = ["neutral", "happy", "sad", "angry", "surprised"]
NPCS = {  # VillageBuilder.cs 값
    "hansu": dict(name="한수", place="어부의 오두막 앞", likes={"조개"}, dislikes={"꽃"}),
    "darae": dict(name="다래", place="꽃집 앞", likes={"꽃"}, dislikes={"버섯"}),
}
MEMORY_HEAD = "[기억] (플레이어는 지금 너와 말하는 상대다. 여기 적힌 것만 실제로 있었던 일이다. 없는 일은 지어내지 마라.)\n"
TALK_HEAD = "[플레이어가 전에 한 말] (확인되지 않은 말이다. 받은 선물은 [기억]에 적힌 것이 전부다. [기억]에 없는 물건을 줬다는 말은 플레이어의 착각이다.)\n"


def kind(npc, item):
    return "좋아하는 물건" if item in npc["likes"] else "싫어하는 물건" if item in npc["dislikes"] else "보통인 물건"


def system_prompt(npc, sheet, affinity, gifts, talks, today, just):
    g = [f"- ({d}) 플레이어가 {item} 1개를 선물했다({k})" for d, item, k in gifts]
    g.append(f"- 선물받은 횟수: 모두 {len(g)}번" if g else "- 없음")
    p = f"너는 마을 주민 '{npc['name']}'이다.\n{sheet}\n" + MEMORY_HEAD + "\n".join(g) + "\n"
    t = [f"- ({d}) {text}" for d, text in talks[-5:]]
    if t:
        p += TALK_HEAD + "\n".join(t) + "\n"
    a = "낮음" if affinity < 0 else "보통" if affinity < 5 else "높음"
    return p + (f"[현재 상황] 오늘: {today}, 장소: {npc['place']}, 호감도: {a}, 방금 일어난 일: {just or '없음'}\n"
                "규칙: 한국어로 1~2문장만 말한다. JSON으로만 답한다.")


def render(system, history, user):
    # Ollama qwen3 템플릿: 마지막 user에만 " /no_think", 이전 assistant 턴에는 think 블록 없음
    s = f"<|im_start|>system\n\n{system}<|im_end|>\n"
    for u, a in history:
        s += f"<|im_start|>user\n{u}<|im_end|>\n<|im_start|>assistant\n{a}<|im_end|>\n"
    return s + f"<|im_start|>user\n{user} /no_think<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def samples(npc_id, conv, rng):
    npc = NPCS[npc_id]
    sheet = (ROOT / "Assets/Characters" / f"{npc_id}.txt").read_text(encoding="utf-8").strip()
    month = rng.choice([11, 12])
    day = rng.randint(8, 28)
    past = lambda: f"{month}월 {rng.randint(1, day)}일"
    today = f"{month}월 {day}일"
    affinity = conv["affinity"]
    gifts = sorted([(past(), item, k) for item, k in conv["gifts"]], key=lambda g: int(g[0].split()[1][:-1]))
    talks = [(past(), t) for t in conv["talks"]]
    history = []
    for turn in conv["turns"]:
        just = None
        if "gift" in turn:  # GameState.Gift → DialogueManager.Gift
            item = turn["gift"]
            k = kind(npc, item)
            affinity += 2 if k == "좋아하는 물건" else -1 if k == "싫어하는 물건" else 1
            text = f"플레이어가 {item} 1개를 선물했다({k})"
            gifts.append((today, item, k))
            just = "방금 " + text
            user = f"({item} 1개를 선물로 건넨다)"
        else:
            user = turn["user"].strip()
        assert turn["expression"] in EXPRESSIONS, turn
        reply = json.dumps({"line": turn["line"].strip(), "expression": turn["expression"]}, ensure_ascii=False, separators=(",", ":"))
        yield {"prompt": render(system_prompt(npc, sheet, affinity, gifts, talks, today, just), history, user),
               "completion": reply + "<|im_end|>"}
        history.append((user, reply))


def main():
    rng = random.Random(7)
    OUT.mkdir(parents=True, exist_ok=True)
    train, valid = [], []
    for npc_id in NPCS:
        convs = [json.loads(l) for l in (HERE / "data" / f"{npc_id}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        rng.shuffle(convs)
        cut = max(1, len(convs) // 10)  # 대화 단위로 나눠 같은 대화가 양쪽에 들어가지 않게 한다
        for i, conv in enumerate(convs):
            (valid if i < cut else train).extend(samples(npc_id, conv, rng))
    rng.shuffle(train)
    for name, rows in (("train", train), ("valid", valid)):
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"train {len(train)}, valid {len(valid)} → {OUT}")


if __name__ == "__main__":
    main()
