using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

// 가까운 NPC나 채집물을 찾아 안내를 띄우고, E로 대화하거나 줍는다. 대화 중에는 이동을 잠근다.
[RequireComponent(typeof(PlayerController))]
public class Interactor : MonoBehaviour
{
    public DialogueManager dialogue;
    public float range = 2.5f;

    void Update()
    {
        var k = Keyboard.current;
        if (k == null) return;

        GetComponent<PlayerController>().enabled = !dialogue.IsOpen;
        if (dialogue.IsOpen)
        {
            if (k.escapeKey.wasPressedThisFrame) dialogue.Close();
            return;
        }

        var npc = Nearest(Npc.All, out float npcDistance);
        var pickup = Nearest(Pickup.All, out float pickupDistance);
        if (npc != null && pickup != null && pickupDistance < npcDistance) npc = null;

        dialogue.ShowHint(npc != null ? "E: 대화"
            : pickup != null ? $"E: {GameState.ItemName(pickup.itemId)} 줍기" : null);
        if (!k.eKey.wasPressedThisFrame) return;

        if (npc != null)
        {
            var toPlayer = Vector3.ProjectOnPlane(transform.position - npc.transform.position, Vector3.up);
            npc.transform.rotation = Quaternion.LookRotation(toPlayer);
            dialogue.Open(npc);
        }
        else if (pickup != null)
        {
            GameState.Add(pickup.itemId, 1);
            GameState.Save();
            Destroy(pickup.gameObject);
            dialogue.RefreshInventory();
        }
    }

    T Nearest<T>(List<T> all, out float distance) where T : Component
    {
        T nearest = null;
        distance = range;
        foreach (var candidate in all)
        {
            float d = Vector3.Distance(transform.position, candidate.transform.position);
            if (d < distance) { distance = d; nearest = candidate; }
        }
        return nearest;
    }
}
