using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

// PLAN.md 스텝 1의 요청 본문을 그대로 보낸다.
public static class OllamaClient
{
    [Serializable] public class Message { public string role, content; }
    [Serializable] class Messages { public List<Message> messages; }
    [Serializable] class Response { public Message message; }

    public static readonly string[] Expressions = { "neutral", "happy", "sad", "angry", "surprised" };

    static readonly string Fixed =
        "\"stream\":false,\"think\":false,\"keep_alive\":\"30m\"," +
        "\"options\":{\"temperature\":0.7,\"num_predict\":120}," +
        "\"format\":{\"type\":\"object\",\"properties\":{\"line\":{\"type\":\"string\"}," +
        "\"expression\":{\"type\":\"string\",\"enum\":[\"" + string.Join("\",\"", Expressions) + "\"]}}," +
        "\"required\":[\"line\",\"expression\"]},";

    // 성공하면 message.content(JSON 문자열)를, 실패나 타임아웃이면 null을 넘긴다.
    public static IEnumerator Chat(string host, string model, List<Message> messages, Action<string> done)
    {
        string body = "{\"model\":\"" + model + "\"," + Fixed
            + JsonUtility.ToJson(new Messages { messages = messages }).Substring(1);
        using var req = new UnityWebRequest(host + "/api/chat", "POST");
        req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");
        req.timeout = 10;
        yield return req.SendWebRequest();

        string content = null;
        if (req.result == UnityWebRequest.Result.Success)
        {
            try { content = JsonUtility.FromJson<Response>(req.downloadHandler.text)?.message?.content; }
            catch (ArgumentException) { }
        }
        else Debug.LogWarning("Ollama 요청 실패: " + req.error);
        done(content);
    }
}
