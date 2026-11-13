using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

// 인벤토리·호감도·기억과 저장. 아이템과 호감도는 여기서만 바뀐다(LLM은 관여하지 않는다).
public static class GameState
{
    [Serializable] public class Stack { public string id; public int count; }
    [Serializable] public class Memory { public string date, type, text; } // type: "gift" | "talk"
    [Serializable] public class NpcState { public string id; public int affinity; public List<Memory> memories = new(); }
    [Serializable] class SaveData { public List<Stack> inventory = new(); public List<NpcState> npcs = new(); }

    public static readonly string[] ItemIds = { "flower", "mushroom", "shell" };
    static readonly string[] ItemNames = { "꽃", "버섯", "조개" };
    public static string ItemName(string id) => ItemNames[Array.IndexOf(ItemIds, id)];

    public static string PathOverride; // 자가 점검이 실제 저장 파일을 건드리지 않게 한다
    static string SavePath => PathOverride ?? Path.Combine(Application.persistentDataPath, "save.json");

    static SaveData data;
    static SaveData Data => data ??= Load();

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void OnPlay() { PathOverride = null; Reset(); } // 측정 도중 끝났어도 실제 저장 파일로 돌아온다

    public static void Reset() => data = null; // 다음 접근 때 파일에서 다시 읽는다

    static SaveData Load()
    {
        if (File.Exists(SavePath))
        {
            try { return JsonUtility.FromJson<SaveData>(File.ReadAllText(SavePath)) ?? new SaveData(); }
            catch (ArgumentException) { Debug.LogWarning("저장 파일이 깨져 새로 시작한다: " + SavePath); }
        }
        return new SaveData();
    }

    public static void Save() => File.WriteAllText(SavePath, JsonUtility.ToJson(Data, true));

    public static int Count(string item) => Data.inventory.Find(s => s.id == item)?.count ?? 0;

    public static void Add(string item, int amount)
    {
        var stack = Data.inventory.Find(s => s.id == item);
        if (stack == null) Data.inventory.Add(stack = new Stack { id = item });
        stack.count += amount;
    }

    public static NpcState Of(string npcId)
    {
        var state = Data.npcs.Find(n => n.id == npcId);
        if (state == null) Data.npcs.Add(state = new NpcState { id = npcId });
        return state;
    }

    public static void Remember(string npcId, string type, string text) =>
        Of(npcId).memories.Add(new Memory { date = DateTime.Now.ToString("M월 d일"), type = type, text = text });

    // 선물: 인벤토리 -1, 호감도 +2(좋아함)/-1(싫어함)/+1(보통), 기억 추가, 저장.
    // 기억에 적은 문장을 돌려준다. 가진 것이 없으면 아무것도 바꾸지 않고 null.
    public static string Gift(Npc npc, string item)
    {
        if (Count(item) <= 0) return null;
        Add(item, -1);
        bool like = Array.IndexOf(npc.likes, item) >= 0, dislike = Array.IndexOf(npc.dislikes, item) >= 0;
        Of(npc.id).affinity += like ? 2 : dislike ? -1 : 1;
        string text = $"플레이어가 {ItemName(item)} 1개를 선물했다({(like ? "좋아하는 물건" : dislike ? "싫어하는 물건" : "보통인 물건")})";
        Remember(npc.id, "gift", text);
        Save();
        return text;
    }
}
