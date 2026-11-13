using System.Collections.Generic;
using UnityEngine;

// 마을에 놓인 채집물. Interactor가 E로 줍는다.
// shortcut: 주운 것은 저장하지 않아 게임을 다시 켜면 다시 놓여 있다, 채집량에 제한이 필요해지면 저장할 것
public class Pickup : MonoBehaviour
{
    public static readonly List<Pickup> All = new();

    public string itemId;

    void OnEnable() => All.Add(this);
    void OnDisable() => All.Remove(this);
}
