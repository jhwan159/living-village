using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.InputSystem;

// 평가용. F2: 조건 전환(일반/성격/성격+기억), F5: 자동 측정.
// 측정은 임시 저장 파일을 쓰므로 실제 저장 데이터는 바뀌지 않는다.
// 결과: persistentDataPath/benchmark.csv (원자료), benchmark_summary.txt (요약)
[RequireComponent(typeof(DialogueManager))]
public class BenchmarkRunner : MonoBehaviour
{
    public int speedRuns = 30;
    public int stateRuns = 20;

    static readonly string[] PersonaQuestions = {
        // 성격 시트(Assets/Characters/*.txt)의 말투 예시와 겹치지 않는 질문만 쓴다. 겹치면 예시를 베낀 답이 점수를 올린다.
        "처음 뵙겠습니다.", "어제는 어떻게 보내셨어요?", "오늘 날씨 어때요?", "싫어하는 게 있으세요?", "이 마을은 어떤 곳이에요?",
        "이 마을에서 뭘 하면 좋을까요?", "지금 기분이 어떠세요?", "주말엔 뭐 하세요?", "이 일을 하신 지 얼마나 됐어요?", "저한테 해 주고 싶은 말 있어요?" };

    // 측정 전에 넣는 기억: 조개 1개, 꽃 1개 선물 + "플레이어는 강아지를 키운다". (질문, 정답)
    static readonly string[,] RecallQuestions = {
        { "제가 전에 뭘 드렸는지 기억나세요?", "조개와 꽃" },
        { "제가 조개를 드린 적 있죠?", "있다" },
        { "제가 꽃을 드린 적 있죠?", "있다" },
        { "제가 드린 버섯은 어땠어요?", "받은 적 없다" },
        { "제가 드린 케이크는 맛있었어요?", "받은 적 없다" },
        { "저번에 드린 책 기억나세요?", "받은 적 없다" },
        { "제가 선물을 몇 번 드렸죠?", "두 번" },
        { "제가 키우는 동물이 뭐라고 했죠?", "강아지" },
        { "제가 고양이를 키운다고 말씀드렸었죠?", "아니다(강아지)" },
        { "제가 드린 것 중에 뭐가 제일 마음에 드셨어요?", "한수: 조개, 다래: 꽃" } };

    string status = "";
    bool running;
    StringBuilder csv;

    void Update()
    {
        var k = Keyboard.current;
        if (k == null || running) return;
        if (k.f2Key.wasPressedThisFrame) Npc.condition = (Npc.Condition)(((int)Npc.condition + 1) % 3);
        if (k.f5Key.wasPressedThisFrame && !GetComponent<DialogueManager>().IsOpen) StartCoroutine(Run());
    }

    void OnGUI() => GUI.Label(new Rect(12, Screen.height - 28, 900, 24),
        $"조건: {Npc.ConditionNames[(int)Npc.condition]} (F2)   측정: F5   {status}");

    public IEnumerator Run()
    {
        running = true;
        var interactor = GameObject.FindWithTag("Player").GetComponent<Interactor>();
        interactor.enabled = false; // 측정 중에는 대화·줍기를 막는다
        var saved = Npc.condition;
        string dir = Application.persistentDataPath;
        GameState.PathOverride = Path.Combine(dir, "benchmark-save.json");
        csv = new StringBuilder("종류,조건,NPC,질문,정답,응답,표정,ms,대체대사\n");
        var summary = new StringBuilder();
        try
        {
            Npc.condition = Npc.Condition.PersonaMemory;
            var first = Npc.All[0];

            // 상태 오류: 선물 → 저장 → 다시 읽기를 반복해 인벤토리와 호감도가 기대와 같은지 본다.
            ClearSave();
            string liked = first.likes[0];
            int stateErrors = 0;
            for (int i = 1; i <= stateRuns; i++)
            {
                GameState.Add(liked, 1);
                GameState.Gift(first, liked);
                GameState.Reset();
                var s = GameState.Of(first.id);
                if (s.affinity != 2 * i || s.memories.Count != i || GameState.Count(liked) != 0) stateErrors++;
            }
            summary.AppendLine($"상태 오류: {stateErrors}/{stateRuns}");

            // 회상 평가용 기억
            ClearSave();
            foreach (var npc in Npc.All)
            {
                GameState.Add("shell", 1);
                GameState.Add("flower", 1);
                GameState.Gift(npc, "shell");
                GameState.Gift(npc, "flower");
                GameState.Remember(npc.id, "talk", "플레이어는 강아지를 키운다");
            }

            yield return Ask("warmup", first, "안녕", ""); // 모델 로딩 시간은 측정에서 제외
            csv.Length = csv.ToString().IndexOf('\n') + 1;

            // 프레임: 추론 중(응답 속도 측정 구간), 그다음 추론 없이 3초.
            // 시작 직후에는 로딩으로 프레임이 멈출 수 있어 대기 측정을 뒤에 둔다.
            var times = new List<float>();
            int fallbacks = 0;
            int frames = Time.frameCount;
            float start = Time.realtimeSinceStartup;
            for (int i = 0; i < speedRuns; i++)
            {
                status = $"측정 중: 응답 속도 {i + 1}/{speedRuns}";
                yield return Ask("speed", first, "요즘 뭐 하고 지내세요?", "");
                times.Add(lastMs);
                if (lastFallback) fallbacks++;
            }
            float busyFps = (Time.frameCount - frames) / (Time.realtimeSinceStartup - start);
            frames = Time.frameCount;
            start = Time.realtimeSinceStartup;
            status = "측정 중: 대기 fps";
            yield return new WaitForSecondsRealtime(3f);
            float idleFps = (Time.frameCount - frames) / (Time.realtimeSinceStartup - start);
            times.Sort();
            summary.AppendLine($"응답 속도({speedRuns}회): 중앙값 {times[times.Count / 2]:F0}ms, p95 {times[Mathf.CeilToInt(times.Count * 0.95f) - 1]:F0}ms, 대체 대사 {fallbacks}회");
            summary.AppendLine($"프레임({Screen.width}x{Screen.height}): 추론 없음 {idleFps:F1}fps, 추론 중 {busyFps:F1}fps");

            // 성격 일치와 회상 정확도: 조건별, NPC별. 응답은 CSV를 직접 읽고 채점한다.
            int total = 3 * Npc.All.Count * (PersonaQuestions.Length + RecallQuestions.GetLength(0)), done = 0;
            for (int c = 0; c < 3; c++)
            {
                Npc.condition = (Npc.Condition)c;
                foreach (var npc in Npc.All)
                {
                    foreach (string q in PersonaQuestions)
                    {
                        status = $"측정 중: 성격·회상 {++done}/{total}";
                        yield return Ask("persona", npc, q, "");
                    }
                    for (int i = 0; i < RecallQuestions.GetLength(0); i++)
                    {
                        status = $"측정 중: 성격·회상 {++done}/{total}";
                        yield return Ask("recall", npc, RecallQuestions[i, 0], RecallQuestions[i, 1]);
                    }
                }
            }

            // Excel이 한글을 읽도록 BOM을 붙인다
            File.WriteAllText(Path.Combine(dir, "benchmark.csv"), csv.ToString(), new UTF8Encoding(true));
            File.WriteAllText(Path.Combine(dir, "benchmark_summary.txt"), summary.ToString());
            status = "측정 완료: " + dir;
            Debug.Log($"BenchmarkRunner 완료 ({dir})\n{summary}");
        }
        finally
        {
            File.Delete(GameState.PathOverride);
            GameState.PathOverride = null;
            GameState.Reset();
            Npc.condition = saved;
            interactor.enabled = true;
            running = false;
        }
    }

    static void ClearSave()
    {
        File.Delete(GameState.PathOverride);
        GameState.Reset();
    }

    float lastMs;
    bool lastFallback;

    // 이력 없이 질문 하나만 보내고 CSV에 한 줄 적는다.
    IEnumerator Ask(string kind, Npc npc, string question, string expected)
    {
        var dialogue = GetComponent<DialogueManager>();
        var messages = new List<OllamaClient.Message> {
            new() { role = "system", content = npc.SystemPrompt() },
            new() { role = "user", content = question } };
        string content = null;
        float start = Time.realtimeSinceStartup;
        yield return OllamaClient.Chat(dialogue.ollamaHost, dialogue.model, messages, c => content = c);
        lastMs = (Time.realtimeSinceStartup - start) * 1000f;
        lastFallback = !DialogueManager.TryParse(content, out string line, out int expression);
        csv.AppendLine(string.Join(",",
            kind, Npc.ConditionNames[(int)Npc.condition], npc.displayName, Quote(question), Quote(expected),
            Quote(lastFallback ? "" : line), lastFallback ? "" : OllamaClient.Expressions[expression],
            lastMs.ToString("F0"), lastFallback ? "1" : "0"));
    }

    static string Quote(string field) => "\"" + field.Replace("\"", "\"\"") + "\"";
}
