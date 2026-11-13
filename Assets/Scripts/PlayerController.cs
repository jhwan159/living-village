using UnityEngine;
using UnityEngine.InputSystem;

// 1인칭: 마우스로 시점(좌우는 몸, 위아래는 카메라), WASD로 이동.
// 꺼 두면 이동이 잠기고 커서가 풀린다(대화 중).
[RequireComponent(typeof(CharacterController))]
public class PlayerController : MonoBehaviour
{
    public float speed = 5f;
    public float lookSpeed = 0.1f; // 마우스 1픽셀당 회전 각도

    Transform cam;
    float pitch;
    float bobTimer;
    const float EyeHeight = 1.56f;

    void Awake() => cam = GetComponentInChildren<Camera>().transform;
    void OnEnable() => Cursor.lockState = CursorLockMode.Locked;
    void OnDisable() => Cursor.lockState = CursorLockMode.None;

    void Update()
    {
        var k = Keyboard.current;
        var m = Mouse.current;
        if (k == null || m == null) return;

        // 에디터에서 Esc로 풀린 커서를 클릭으로 다시 잡는다
        if (m.leftButton.wasPressedThisFrame) Cursor.lockState = CursorLockMode.Locked;

        var look = m.delta.ReadValue() * lookSpeed;
        transform.Rotate(0f, look.x, 0f);
        pitch = Mathf.Clamp(pitch - look.y, -80f, 80f);

        var input = new Vector2(
            (k.dKey.isPressed ? 1 : 0) - (k.aKey.isPressed ? 1 : 0),
            (k.wKey.isPressed ? 1 : 0) - (k.sKey.isPressed ? 1 : 0));
        Step(input, Time.deltaTime);

        // 1인칭 몰입감: 걸을 때 자연스러운 보행 시점 흔들림(Head-bob)과 호흡 움직임
        float moveAmount = Mathf.Clamp01(input.magnitude);
        bobTimer += Time.deltaTime * (moveAmount > 0.1f ? 9.5f : 1.6f);
        float bobY = Mathf.Sin(bobTimer) * (moveAmount > 0.1f ? 0.032f : 0.006f);
        float bobX = Mathf.Cos(bobTimer * 0.5f) * (moveAmount > 0.1f ? 0.016f : 0.002f);
        float roll = -input.x * 0.6f + Mathf.Sin(bobTimer * 0.5f) * (moveAmount * 0.35f);
        cam.localPosition = new Vector3(bobX, EyeHeight + bobY, 0f);
        cam.localRotation = Quaternion.Euler(pitch, 0f, roll);
    }

    // 입력을 몸이 보는 방향 기준으로 바꿔 이동한다. 자가 점검에서도 직접 호출한다.
    public void Step(Vector2 input, float dt)
    {
        var move = Vector3.ClampMagnitude(transform.forward * input.y + transform.right * input.x, 1f);
        // shortcut: 평지 전용으로 일정한 힘으로만 아래로 누른다, 점프나 경사가 생기면 수직 속도를 누적할 것
        GetComponent<CharacterController>().Move((move * speed + Vector3.down * 5f) * dt);
    }
}
