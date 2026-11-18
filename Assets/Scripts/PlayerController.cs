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

        // 시점 흔들림(head-bob/roll)은 멀미를 일으켜 뺐다. 눈높이는 빌더가 정한다.
        cam.localRotation = Quaternion.Euler(pitch, 0f, 0f);
    }

    // 입력을 몸이 보는 방향 기준으로 바꿔 이동한다. 자가 점검에서도 직접 호출한다.
    public void Step(Vector2 input, float dt)
    {
        var move = Vector3.ClampMagnitude(transform.forward * input.y + transform.right * input.x, 1f);
        // shortcut: 평지 전용으로 일정한 힘으로만 아래로 누른다, 점프나 경사가 생기면 수직 속도를 누적할 것
        GetComponent<CharacterController>().Move((move * speed + Vector3.down * 5f) * dt);
    }
}
