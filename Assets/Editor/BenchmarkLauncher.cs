using System.Collections;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

// 에디터를 손으로 조작하지 않고 자동 측정을 돌린다(F5와 같은 측정). 끝나면 Unity를 닫는다.
//   Unity -batchmode -projectPath . -executeMethod BenchmarkLauncher.Run -logFile Logs/benchmark.log
// shortcut: 배치 모드에서는 화면을 그리지 않아 fps 줄은 의미가 없다, fps가 필요하면 에디터에서 F5로 잴 것
public static class BenchmarkLauncher
{
    const string Flag = "BenchmarkLauncher.running"; // 플레이 모드로 들어갈 때 스크립트가 다시 로드돼도 남는다

    public static void Run()
    {
        EditorSceneManager.OpenScene("Assets/Scenes/Village.unity");
        SessionState.SetBool(Flag, true);
        EditorApplication.delayCall += EditorApplication.EnterPlaymode;
    }

    [InitializeOnLoadMethod]
    static void Hook() => EditorApplication.playModeStateChanged += state =>
    {
        if (!SessionState.GetBool(Flag, false)) return;
        if (state == PlayModeStateChange.EnteredPlayMode)
        {
            var runner = Object.FindFirstObjectByType<BenchmarkRunner>();
            runner.StartCoroutine(RunThenStop(runner));
        }
        else if (state == PlayModeStateChange.EnteredEditMode)
        {
            SessionState.EraseBool(Flag);
            EditorApplication.Exit(0);
        }
    };

    static IEnumerator RunThenStop(BenchmarkRunner runner)
    {
        yield return runner.Run();
        EditorApplication.ExitPlaymode();
    }
}
