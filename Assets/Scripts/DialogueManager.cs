using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

// 대화 UI를 코드로 만들고, 플레이어 입력을 LLM에 보내 대사를 표시한다.
public class DialogueManager : MonoBehaviour
{
    public string ollamaHost = "http://localhost:11434";
    public string model = "qwen3:8b";

    // OllamaClient.Expressions와 같은 순서
    static readonly string[] ExpressionLabels = { "", " (기쁨)", " (슬픔)", " (화남)", " (놀람)" };

    [Serializable] class Reply { public string line, expression; }

    const string RememberPrompt =
        "[지시] 대화가 끝났다. 이번 대화에서 플레이어가 말한 것 중 나중에도 기억할 사실 하나를 " +
        "'플레이어는 ...' 형태의 평서문 한 문장으로 line에 적어라. 기억할 것이 없으면 line에 '없음'만 적어라.";

    GameObject panel;
    Text hint, nameText, lineText, inventoryText;
    InputField input;
    Font font;
    readonly Button[] giftButtons = new Button[GameState.ItemIds.Length];

    Npc npc;
    int session;
    bool waiting, talked;
    readonly List<OllamaClient.Message> messages = new();

    public bool IsOpen => panel.activeSelf;

    void Awake()
    {
        BuildUi();
        RefreshInventory();
    }

    // 메시지 없는 요청은 Ollama가 모델만 메모리에 올린다. 첫 대화가 로딩 때문에 타임아웃(10초)에 걸리지 않게 한다.
    void Start() => StartCoroutine(OllamaClient.Chat(ollamaHost, model, new List<OllamaClient.Message>(), _ => { }, 120));

    public void ShowHint(string text)
    {
        hint.enabled = text != null;
        hint.text = text ?? "";
    }

    // 인벤토리 표시와 선물 버튼(가진 것만 누를 수 있다)을 현재 개수에 맞춘다.
    public void RefreshInventory()
    {
        var parts = new List<string>();
        for (int i = 0; i < giftButtons.Length; i++)
        {
            string id = GameState.ItemIds[i];
            string label = $"{GameState.ItemName(id)} {GameState.Count(id)}";
            parts.Add(label);
            giftButtons[i].interactable = GameState.Count(id) > 0;
            giftButtons[i].GetComponentInChildren<Text>().text = "선물: " + label;
        }
        inventoryText.text = string.Join("   ", parts);
    }

    public void Open(Npc target)
    {
        npc = target;
        session++;
        waiting = talked = false;
        messages.Clear();
        messages.Add(new OllamaClient.Message { role = "system" });
        nameText.text = npc.displayName;
        lineText.text = "";
        ShowHint(null);
        panel.SetActive(true);
        input.text = "";
        input.ActivateInputField();
    }

    public void Close()
    {
        session++; // 아직 오지 않은 응답은 번호가 달라져 버려진다
        panel.SetActive(false);
        if (!talked) return;

        // 이번 대화에서 기억할 사실 한 문장을 받아 저장한다. 실패하면 기억하지 않는다.
        var target = npc;
        var log = new List<OllamaClient.Message>(messages) { new() { role = "user", content = RememberPrompt } };
        StartCoroutine(OllamaClient.Chat(ollamaHost, model, log, content =>
        {
            if (!TryParse(content, out string fact, out _) || fact.Trim('.', ' ') == "없음") return;
            // 선물은 GameState.Gift만 기록한다. 플레이어가 "사과 드렸죠"라고 한 말이 기억으로 남으면 안 된다.
            // shortcut: 낱말로만 거른다, 다른 표현으로 새는 것이 측정에서 보이면 요약 프롬프트를 고칠 것
            if (System.Text.RegularExpressions.Regex.IsMatch(fact, "선물|줬|주었|드렸|건넸|건네")) return;
            GameState.Remember(target.id, "talk", fact);
            GameState.Save();
        }));
    }

    void Send(string text)
    {
        input.text = "";
        input.ActivateInputField();
        if (!IsOpen || waiting || string.IsNullOrWhiteSpace(text)) return;
        talked = true;
        Ask(text.Trim(), null);
    }

    void Gift(string item)
    {
        if (!IsOpen || waiting) return;
        string result = GameState.Gift(npc, item); // 결과는 게임 코드가 정하고, LLM에는 반응 대사만 맡긴다
        if (result == null) return;
        RefreshInventory();
        Ask($"({GameState.ItemName(item)} 1개를 선물로 건넨다)", "방금 " + result);
        input.ActivateInputField();
    }

    void Ask(string text, string justHappened)
    {
        messages[0].content = npc.SystemPrompt(justHappened); // 기억과 호감도가 바뀌었을 수 있어 매번 다시 만든다
        var user = new OllamaClient.Message { role = "user", content = text };
        messages.Add(user);
        waiting = true;
        nameText.text = npc.displayName;
        lineText.text = "…";
        int id = session;
        StartCoroutine(OllamaClient.Chat(ollamaHost, model, messages, content =>
        {
            if (id != session) return;
            waiting = false;
            if (TryParse(content, out string line, out int expression))
                messages.Add(new OllamaClient.Message { role = "assistant", content = content });
            else
            {
                messages.Remove(user); // 실패한 턴은 이력에 남기지 않는다
                line = npc.fallbackLines[UnityEngine.Random.Range(0, npc.fallbackLines.Length)];
            }
            // shortcut: 표정은 이름 옆 글자로만 보여 준다, 머리 위 아이콘이 필요해지면 교체할 것
            nameText.text = npc.displayName + ExpressionLabels[expression];
            lineText.text = line;
        }));
    }

    // LLM 응답 검사: JSON이 아니거나, 대사가 비었거나 너무 길거나, 외국 문자가 섞였거나, 표정이 목록 밖이면 false.
    public static bool TryParse(string content, out string line, out int expression)
    {
        line = null;
        expression = 0;
        if (string.IsNullOrEmpty(content)) return false;
        Reply reply;
        try { reply = JsonUtility.FromJson<Reply>(content); }
        catch (ArgumentException) { return false; }
        int index = reply == null ? -1 : Array.IndexOf(OllamaClient.Expressions, reply.expression);
        if (index < 0 || string.IsNullOrWhiteSpace(reply.line) || reply.line.Length > 200) return false;
        // qwen3가 가끔 한자·가나·키릴 문자를 섞는다(측정에서 150개 중 5~6개)
        if (System.Text.RegularExpressions.Regex.IsMatch(reply.line, "[一-鿿぀-ヿЀ-ӿ]")) return false;
        line = reply.line.Trim();
        expression = index;
        return true;
    }

    void BuildUi()
    {
        // shortcut: TMP 한글 폰트 에셋 대신 OS 한글 폰트를 쓴다, 두 폰트가 없는 OS로 배포하면 폰트 파일을 넣을 것
        font = Font.CreateDynamicFontFromOSFont(new[] { "Apple SD Gothic Neo", "Malgun Gothic" }, 32);

        var canvas = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        canvas.transform.SetParent(transform);
        canvas.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
        var scaler = canvas.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule))
            .transform.SetParent(transform);

        hint = Label(canvas.transform, "E: 대화", 36, TextAnchor.MiddleCenter, new Vector2(0f, 0.36f), new Vector2(1f, 0.42f));
        hint.enabled = false;
        // shortcut: 인벤토리는 아이콘 없이 글자로만 보여 준다, 아이템 종류가 늘면 아이콘 UI로 바꿀 것
        inventoryText = Label(canvas.transform, "", 30, TextAnchor.UpperLeft, new Vector2(0.02f, 0.9f), new Vector2(0.5f, 0.97f));

        panel = Box(canvas.transform, new Color(0f, 0f, 0f, 0.75f), new Vector2(0.1f, 0.04f), new Vector2(0.9f, 0.34f)).gameObject;
        nameText = Label(panel.transform, "", 34, TextAnchor.UpperLeft, new Vector2(0.03f, 0.74f), new Vector2(0.5f, 0.95f));
        nameText.color = new Color(1f, 0.85f, 0.4f);
        for (int i = 0; i < giftButtons.Length; i++)
        {
            string item = GameState.ItemIds[i];
            float x = 0.52f + 0.15f * i;
            var box = Box(panel.transform, new Color(0.25f, 0.4f, 0.3f), new Vector2(x, 0.76f), new Vector2(x + 0.14f, 0.94f));
            giftButtons[i] = box.gameObject.AddComponent<Button>();
            giftButtons[i].onClick.AddListener(() => Gift(item));
            Label(box.transform, "", 24, TextAnchor.MiddleCenter, Vector2.zero, Vector2.one);
        }
        lineText = Label(panel.transform, "", 32, TextAnchor.UpperLeft, new Vector2(0.03f, 0.3f), new Vector2(0.97f, 0.72f));

        var field = Box(panel.transform, Color.white, new Vector2(0.03f, 0.06f), new Vector2(0.82f, 0.24f));
        input = field.gameObject.AddComponent<InputField>();
        input.textComponent = Label(field.transform, "", 30, TextAnchor.MiddleLeft, new Vector2(0.01f, 0f), new Vector2(0.99f, 1f));
        input.textComponent.color = Color.black;
        input.textComponent.supportRichText = false;
        var placeholder = Label(field.transform, "할 말을 입력하고 Enter", 30, TextAnchor.MiddleLeft, new Vector2(0.01f, 0f), new Vector2(0.99f, 1f));
        placeholder.color = Color.gray;
        input.placeholder = placeholder;
        input.onSubmit.AddListener(Send);

        var close = Box(panel.transform, new Color(0.3f, 0.3f, 0.3f), new Vector2(0.84f, 0.06f), new Vector2(0.97f, 0.24f));
        close.gameObject.AddComponent<Button>().onClick.AddListener(Close);
        Label(close.transform, "닫기 (Esc)", 26, TextAnchor.MiddleCenter, Vector2.zero, Vector2.one);

        panel.SetActive(false);
    }

    // 부모 영역의 비율(min~max)로 자리를 잡는다.
    static T Element<T>(Transform parent, Vector2 min, Vector2 max) where T : Component
    {
        var rect = new GameObject(typeof(T).Name, typeof(RectTransform)).GetComponent<RectTransform>();
        rect.SetParent(parent, false);
        rect.anchorMin = min;
        rect.anchorMax = max;
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        return rect.gameObject.AddComponent<T>();
    }

    static Image Box(Transform parent, Color color, Vector2 min, Vector2 max)
    {
        var image = Element<Image>(parent, min, max);
        image.color = color;
        return image;
    }

    Text Label(Transform parent, string text, int size, TextAnchor anchor, Vector2 min, Vector2 max)
    {
        var label = Element<Text>(parent, min, max);
        label.font = font;
        label.fontSize = size;
        label.alignment = anchor;
        label.text = text;
        return label;
    }
}
