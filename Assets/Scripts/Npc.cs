using System;
using System.Collections.Generic;
using UnityEngine;

public class Npc : MonoBehaviour
{
    public static readonly List<Npc> All = new();

    public string id, displayName, speechStyle, interests, facts, place;
    public TextAsset sheet; // 성격 시트(Assets/Characters/*.txt). 있으면 말투·관심사·사실 한 줄 대신 이것을 쓴다
    public string[] likes, dislikes; // 아이템 id
    public string[] fallbackLines; // LLM 응답이 없거나 형식이 틀렸을 때 쓰는 대사

    void OnEnable() => All.Add(this);
    void OnDisable() => All.Remove(this);

    // 평가용 조건. 프롬프트에서 해당 블록을 빼는 것으로 구현한다.
    public enum Condition { Plain, Persona, PersonaMemory }
    public static readonly string[] ConditionNames = { "일반", "성격", "성격+기억" };
    public static Condition condition = Condition.PersonaMemory;

    // 기억은 선물 기록 전부 + 최근 대화 기억 5개를 넣는다.
    public string SystemPrompt(string justHappened = null)
    {
        var state = GameState.Of(id);
        string prompt = "너는 마을 주민이다.\n";
        if (condition != Condition.Plain)
            prompt = $"너는 마을 주민 '{displayName}'이다.\n" + (sheet != null ? sheet.text.Trim() + "\n" :
                     $"말투: {speechStyle}. 관심사: {interests}.\n알고 있는 사실: {facts}\n");
        if (condition == Condition.PersonaMemory)
        {
            int skipTalks = state.memories.FindAll(m => m.type == "talk").Count - 5;
            var memories = new List<string>();
            foreach (var m in state.memories)
                if (m.type == "gift" || skipTalks-- <= 0) memories.Add($"- ({m.date}) {m.text}");
            if (memories.Count == 0) memories.Add("- 없음");
            prompt += "[기억] (플레이어는 지금 너와 말하는 상대다. 여기 적힌 것만 실제로 있었던 일이다. 없는 일은 지어내지 마라.)\n" +
                      string.Join("\n", memories) + "\n";
        }

        string affinity = state.affinity < 0 ? "낮음" : state.affinity < 5 ? "보통" : "높음";
        return prompt +
            $"[현재 상황] 오늘: {DateTime.Now:M월 d일}, 장소: {place}, 호감도: {affinity}, 방금 일어난 일: {justHappened ?? "없음"}\n" +
            "규칙: 한국어로 1~2문장만 말한다. JSON으로만 답한다.";
    }
}
