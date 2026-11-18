using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;

// Blender 5.3에서 제작한 PBR 건축물·도로·식생·캐릭터 에셋으로 몰입형 1인칭 마을 씬을 구성한다. 메뉴: Tools > Build Village
public static class VillageBuilder
{
    const string ScenePath = "Assets/Scenes/Village.unity";
    const string BlenderModels = "Assets/Blender/Models/";
    const string BlenderTextures = "Assets/Blender/Textures/";
    const string Characters = "Assets/Kenney/Characters/";
    const string ControllerPath = "Assets/Animations/Character.controller";

    static readonly Dictionary<string, Material> PbrMats = new();

    [MenuItem("Tools/Build Village")]
    public static void Build()
    {
        ShaderUtil.allowAsyncCompilation = false;
        AssetDatabase.Refresh();
        SetupPbrLibrary();

        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        // 1. 태양광 (따뜻한 오후 햇살 + 긴 입체 그림자)
        var light = new GameObject("Sun").AddComponent<Light>();
        light.type = LightType.Directional;
        light.shadows = LightShadows.Soft;
        light.shadowStrength = 0.85f;
        light.transform.rotation = Quaternion.Euler(32f, -35f, 0f);
        light.color = new Color(1f, 0.93f, 0.80f);
        light.intensity = 1.65f;

        // 반대편 그림자 영역의 디테일을 살리는 하늘 반사 보조광
        var fillLight = new GameObject("SkyFillLight").AddComponent<Light>();
        fillLight.type = LightType.Directional;
        fillLight.shadows = LightShadows.None;
        fillLight.transform.rotation = Quaternion.Euler(48f, 145f, 0f);
        fillLight.color = new Color(0.62f, 0.76f, 0.95f);
        fillLight.intensity = 0.42f;

        // 2. 파노라마 스카이박스·안개·주변광(Trilight GI)
        var skyTex = LoadTex("Sky_Panorama.png", false, false);
        var sky = Mat("Sky", Color.white, "Skybox/Panoramic");
        sky.SetTexture("_MainTex", skyTex);
        sky.SetFloat("_Exposure", 1.15f);
        RenderSettings.skybox = sky;
        RenderSettings.sun = light;
        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Trilight;
        RenderSettings.ambientSkyColor = new Color(0.66f, 0.78f, 0.94f);
        RenderSettings.ambientEquatorColor = new Color(0.68f, 0.65f, 0.60f);
        RenderSettings.ambientGroundColor = new Color(0.34f, 0.38f, 0.30f);
        var haze = new Color(0.78f, 0.85f, 0.92f);
        RenderSettings.fog = true;
        RenderSettings.fogMode = FogMode.Linear;
        RenderSettings.fogColor = haze;
        RenderSettings.fogStartDistance = 36f;
        RenderSettings.fogEndDistance = 175f;

        // 3. 후처리(ACES 톤매핑·블룸·비네트) + 실시간 반사 프로브
        var volume = new GameObject("PostProcessing").AddComponent<UnityEngine.Rendering.Volume>();
        volume.sharedProfile = AssetDatabase.LoadAssetAtPath<UnityEngine.Rendering.VolumeProfile>("Assets/Settings/SampleSceneProfile.asset");

        var probeGo = new GameObject("VillageReflectionProbe");
        probeGo.transform.position = new Vector3(0f, 3.5f, 0f);
        var probe = probeGo.AddComponent<ReflectionProbe>();
        probe.mode = UnityEngine.Rendering.ReflectionProbeMode.Realtime;
        probe.refreshMode = UnityEngine.Rendering.ReflectionProbeRefreshMode.OnAwake;
        probe.size = new Vector3(120f, 30f, 120f);
        probe.resolution = 256;
        probe.intensity = 1.0f;

        // 4. PBR 잔디 지면 + 돌길·광장·항구 부두 환경
        var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.name = "Ground";
        ground.transform.localScale = new Vector3(40f, 1f, 40f);
        var grassMat = PbrMat("Grass", new Color(0.78f, 0.84f, 0.72f), 0.25f, 0f, "Grass_Albedo.png", "Grass_Normal.png", 1.1f, 65f);
        ground.GetComponent<Renderer>().sharedMaterial = grassMat;

        var env = InstantiateRaw(BlenderModels + "Village_Environment.fbx", "Village_Environment", Vector3.zero, 0f);
        ApplyPbrMaterials(env);

        // 마을 밖으로 나가지 못하게 하는 보이지 않는 벽
        foreach (var (pos, size) in new[] {
            (new Vector3(0, 2, 30), new Vector3(60, 4, 1)), (new Vector3(0, 2, -30), new Vector3(60, 4, 1)),
            (new Vector3(30, 2, 0), new Vector3(1, 4, 60)), (new Vector3(-30, 2, 0), new Vector3(1, 4, 60)) })
        {
            var wall = new GameObject("Boundary").AddComponent<BoxCollider>();
            wall.transform.position = pos;
            wall.size = size;
        }

        // 5. 인조이 스타일 4개 주요 건축물 배치
        var north = Building("House_North", "Building_North_Residence", new Vector3(0, 0, 12), 180f);
        Building("House_East", "Building_East_Cafe", new Vector3(15, 0, 2), 270f);
        Building("FlowerShop", "Building_FlowerShop_Darae", new Vector3(-15, 0, 4), 90f);
        Building("FisherHut", "Building_FisherHut_Hansu", new Vector3(12, 0, -15), 270f);

        // 6. 가로등(실제 포인트 라이트 포함) 및 벤치 배치 (테스트 이동 경로인 X축 서쪽·Z축 북쪽 중앙선은 비워 둠)
        var lampSpots = new[] {
            (new Vector3(-2.6f, 0f, 6.2f), 0f),
            (new Vector3(2.6f, 0f, 6.2f), 180f),
            (new Vector3(-8.5f, 0f, 6.8f), -90f),
            (new Vector3(8.5f, 0f, 4.2f), 90f),
            (new Vector3(7.2f, 0f, -10.5f), 180f),
            (new Vector3(-3.8f, 0f, -4.2f), 45f),
        };
        foreach (var (lpos, lyaw) in lampSpots)
        {
            var lamp = Model(BlenderModels + "Prop_StreetLamp.fbx", "StreetLamp", lpos, lyaw, 3.6f, false);
            var pt = new GameObject("LampLight").AddComponent<Light>();
            pt.type = LightType.Point;
            pt.color = new Color(1f, 0.84f, 0.58f);
            pt.intensity = 2.2f;
            pt.range = 9.5f;
            pt.shadows = LightShadows.None;
            pt.transform.SetParent(lamp.transform, false);
            pt.transform.localPosition = new Vector3(0.45f, 3.1f, 0f);
        }

        var benchSpots = new[] {
            (new Vector3(-4.2f, 0f, 3.2f), 135f),
            (new Vector3(4.2f, 0f, 3.2f), -135f),
            (new Vector3(4.2f, 0f, -3.5f), -45f),
        };
        foreach (var (bpos, byaw) in benchSpots)
            Model(BlenderModels + "Prop_Bench.fbx", "Bench", bpos, byaw, 0.85f, false);

        // 7. 고디테일 나무 및 외곽 숲 배치
        var trees = new[] { "Tree_Realistic_Oak", "Tree_Realistic_Birch", "Tree_Realistic_Pine" };
        var treeSpots = new[] { new Vector3(-8, 0, 16), new Vector3(9, 0, 18), new Vector3(-20, 0, -6),
                                new Vector3(-12, 0, -16), new Vector3(22, 0, 12), new Vector3(22, 0, -6),
                                new Vector3(-22, 0, 16), new Vector3(2, 0, -20) };
        for (int i = 0; i < treeSpots.Length; i++)
        {
            var tree = Model(BlenderModels + trees[i % trees.Length] + ".fbx", "Tree", treeSpots[i], i * 65f, 5.4f, false);
            var trunk = tree.AddComponent<CapsuleCollider>();
            float s = tree.transform.localScale.y;
            trunk.radius = 0.35f / s;
            trunk.height = 4f / s;
            trunk.center = Vector3.up * 2f / s;
        }
        // 울타리 밖 숲
        for (int i = 0; i < 64; i++)
        {
            float angle = i * Mathf.PI * 2f / 32f + (i < 32 ? 0f : 0.10f), radius = (i < 32 ? 39f : 52f) + i % 3 * 3f;
            Model(BlenderModels + trees[i % trees.Length] + ".fbx", "FarTree",
                new Vector3(Mathf.Cos(angle), 0, Mathf.Sin(angle)) * radius, i * 47f, 6.5f + i % 4, false);
        }

        // 8. 1인칭 플레이어 및 카메라
        var player = new GameObject("Player");
        player.tag = "Player";
        var cc = player.AddComponent<CharacterController>();
        cc.height = 1.6f;
        cc.radius = 0.4f;
        cc.center = Vector3.up * 0.8f;
        var controller = player.AddComponent<PlayerController>();

        var cam = new GameObject("Main Camera").AddComponent<Camera>();
        cam.tag = "MainCamera";
        cam.fieldOfView = 72f;
        cam.nearClipPlane = 0.1f;
        var camData = cam.gameObject.AddComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>();
        camData.renderPostProcessing = true;
        camData.antialiasing = UnityEngine.Rendering.Universal.AntialiasingMode.SubpixelMorphologicalAntiAliasing;
        cam.gameObject.AddComponent<AudioListener>();
        cam.transform.SetParent(player.transform, false);
        cam.transform.localPosition = Vector3.up * 1.56f;

        // 9. NPC 배치. 한수와 다래는 뼈대가 달라 애니메이션 컨트롤러를 따로 만든다.
        var idle = CharacterAnimator(BlenderModels + "Character_Hansu.fbx", ControllerPath);
        var fisher = Npc("Character_Hansu", new Vector3(5.5f, 0, -15), idle);
        fisher.id = "hansu";
        fisher.likes = new[] { "shell" };
        fisher.dislikes = new[] { "flower" };
        fisher.displayName = "한수";
        fisher.sheet = AssetDatabase.LoadAssetAtPath<TextAsset>("Assets/Characters/hansu.txt");
        if (fisher.sheet == null) throw new System.Exception("성격 시트 없음: hansu.txt");
        fisher.place = "어부의 오두막 앞";
        fisher.fallbackLines = new[] { "…음.", "뭐라고? 잘 못 들었다.", "바다나 보러 가야겠군.", "나중에 얘기하지." };

        var florist = Npc("Character_Darae", new Vector3(-8.5f, 0, 4),
            CharacterAnimator(BlenderModels + "Character_Darae.fbx", "Assets/Animations/Character_Darae.controller"));
        florist.id = "darae";
        florist.likes = new[] { "flower" };
        florist.dislikes = new[] { "mushroom" };
        florist.displayName = "다래";
        florist.sheet = AssetDatabase.LoadAssetAtPath<TextAsset>("Assets/Characters/darae.txt");
        if (florist.sheet == null) throw new System.Exception("성격 시트 없음: darae.txt");
        florist.place = "꽃집 앞";
        florist.fallbackLines = new[] { "어머, 잠깐 딴생각을 했네요.", "죄송해요, 다시 말씀해 주시겠어요?", "꽃에 물 줄 시간이라 정신이 없네요.", "아, 그 얘기는 다음에 해요!" };

        // 10. 고디테일 채집물(꽃다발·버섯 군락·가리비 조개) 배치
        var flowerSpots = new[] { new Vector3(-9, 0, 9), new Vector3(-12, 0, -3), new Vector3(-5, 0, -8) };
        var mushroomSpots = new[] { new Vector3(-7, 0, 15), new Vector3(8, 0, 17), new Vector3(-19, 0, -7) };
        var shellSpots = new[] { new Vector3(8, 0, -8), new Vector3(4, 0, -21), new Vector3(19, 0, -22) };
        for (int i = 0; i < 3; i++)
        {
            Pickup(Model(BlenderModels + "Pickup_Flower.fbx", "Flower", flowerSpots[i], i * 45f, 0.55f, false), "flower");
            Pickup(Model(BlenderModels + "Pickup_Mushroom.fbx", "Mushroom", mushroomSpots[i], i * 60f, 0.35f, false), "mushroom");
            Pickup(Model(BlenderModels + "Pickup_Shell.fbx", "Shell", shellSpots[i], i * 35f, 0.36f, true), "shell");
        }

        var dialogue = new GameObject("Dialogue").AddComponent<DialogueManager>();
        dialogue.gameObject.AddComponent<BenchmarkRunner>();
        player.AddComponent<Interactor>().dialogue = dialogue;

        SelfCheck(controller, north.GetComponent<Collider>().bounds);
        GiftCheck(fisher);

        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
        PlayerSettings.runInBackground = true;
        EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(), ScenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };

        Screenshot(cam, "Logs/village.png");
        // 다래와 꽃집 앞 1인칭 시점 프리뷰
        cam.transform.position = new Vector3(-6.4f, 1.56f, 2.8f);
        cam.transform.rotation = Quaternion.LookRotation(new Vector3(-10.5f, 1.52f, 4.0f) - cam.transform.position);
        Screenshot(cam, "Logs/village_darae.png");
        // 다래 캐릭터 클로즈업 프리뷰 (얼굴·헤어·앞치마·꽃바구니 컨셉 확인용)
        var daraeLookDir = (florist.transform.position + florist.transform.forward * 1.45f) - florist.transform.position;
        cam.transform.position = florist.transform.position + florist.transform.forward * 1.55f + Vector3.up * 1.25f;
        cam.transform.rotation = Quaternion.LookRotation((florist.transform.position + Vector3.up * 1.15f) - cam.transform.position);
        Screenshot(cam, "Logs/village_darae_closeup.png");
        // 한수와 어부 오두막·항구 1인칭 시점 프리뷰
        cam.transform.position = new Vector3(3.4f, 1.56f, -13.8f);
        cam.transform.rotation = Quaternion.LookRotation(new Vector3(7.5f, 1.52f, -15.2f) - cam.transform.position);
        Screenshot(cam, "Logs/village_hansu.png");

        cam.transform.localPosition = Vector3.up * 1.56f;
        cam.transform.localRotation = Quaternion.identity;
        EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(), ScenePath);
        Debug.Log("VillageBuilder: OK");
    }

    static void SetupPbrLibrary()
    {
        PbrMats.Clear();
        PbrMats["Mat_Stucco"] = PbrMat("Mat_Stucco", new Color(0.94f, 0.91f, 0.86f), 0.32f, 0f, "Stucco_Albedo.png", "Stucco_Normal.png", 0.8f, 2f);
        PbrMats["Mat_StuccoWarm"] = PbrMat("Mat_StuccoWarm", new Color(0.96f, 0.89f, 0.80f), 0.35f, 0f, "Stucco_Albedo.png", "Stucco_Normal.png", 0.8f, 2f);
        PbrMats["Mat_StuccoSage"] = PbrMat("Mat_StuccoSage", new Color(0.74f, 0.82f, 0.73f), 0.38f, 0f, "Stucco_Albedo.png", "Stucco_Normal.png", 0.7f, 2f);
        PbrMats["Mat_Brick"] = PbrMat("Mat_Brick", new Color(0.88f, 0.82f, 0.78f), 0.28f, 0f, "Brick_Albedo.png", "Brick_Normal.png", 1.15f, 1.5f);
        PbrMats["Mat_Wood"] = PbrMat("Mat_Wood", new Color(0.88f, 0.82f, 0.76f), 0.48f, 0f, "Wood_Albedo.png", "Wood_Normal.png", 1.0f, 1.5f);
        PbrMats["Mat_DarkWood"] = PbrMat("Mat_DarkWood", new Color(0.48f, 0.36f, 0.26f), 0.45f, 0f, "Wood_Albedo.png", "Wood_Normal.png", 1.0f, 1.5f);
        PbrMats["Mat_Concrete"] = PbrMat("Mat_Concrete", new Color(0.74f, 0.73f, 0.71f), 0.35f, 0f, "Stucco_Albedo.png", "Stucco_Normal.png", 0.9f, 2f);
        PbrMats["Mat_Cobble"] = PbrMat("Mat_Cobble", new Color(0.85f, 0.84f, 0.82f), 0.42f, 0f, "Cobble_Albedo.png", "Cobble_Normal.png", 1.25f, 1.8f);
        PbrMats["Mat_RoofSlate"] = PbrMat("Mat_RoofSlate", new Color(0.75f, 0.78f, 0.82f), 0.52f, 0.1f, "Roof_Albedo.png", "Roof_Normal.png", 1.2f, 2f);
        PbrMats["Mat_RoofTerracotta"] = PbrMat("Mat_RoofTerracotta", new Color(0.86f, 0.44f, 0.30f), 0.48f, 0f, null, "Roof_Normal.png", 1.2f, 2f);
        PbrMats["Mat_DarkMetal"] = PbrMat("Mat_DarkMetal", new Color(0.18f, 0.20f, 0.22f), 0.78f, 0.85f);
        PbrMats["Mat_Brass"] = PbrMat("Mat_Brass", new Color(0.90f, 0.72f, 0.34f), 0.85f, 0.90f);
        PbrMats["Mat_Glass"] = PbrMat("Mat_Glass", new Color(0.20f, 0.32f, 0.44f), 0.95f, 0.25f);
        PbrMats["Mat_WarmGlow"] = PbrMat("Mat_WarmGlow", new Color(1f, 0.90f, 0.68f), 0.80f, 0f, null, null, 1f, 1f, new Color(1.45f, 1.15f, 0.72f));
        PbrMats["Mat_AwningStripe"] = PbrMat("Mat_AwningStripe", new Color(0.85f, 0.34f, 0.26f), 0.30f, 0f);
        PbrMats["Mat_Foliage"] = PbrMat("Mat_Foliage", new Color(0.28f, 0.50f, 0.23f), 0.32f, 0f, null, "Grass_Normal.png", 0.7f, 2f);
        PbrMats["Mat_FoliageLight"] = PbrMat("Mat_FoliageLight", new Color(0.36f, 0.58f, 0.26f), 0.35f, 0f, null, "Grass_Normal.png", 0.7f, 2f);
        PbrMats["Mat_PineNeedles"] = PbrMat("Mat_PineNeedles", new Color(0.20f, 0.40f, 0.22f), 0.30f, 0f, null, "Grass_Normal.png", 0.8f, 2f);
        PbrMats["Mat_Bark"] = PbrMat("Mat_Bark", new Color(0.42f, 0.31f, 0.22f), 0.22f, 0f, null, "Wood_Normal.png", 1.2f, 2f);
        PbrMats["Mat_BirchBark"] = PbrMat("Mat_BirchBark", new Color(0.86f, 0.83f, 0.78f), 0.30f, 0f, null, "Wood_Normal.png", 0.9f, 2f);
        PbrMats["Mat_FlowerRed"] = PbrMat("Mat_FlowerRed", new Color(0.90f, 0.22f, 0.26f), 0.48f, 0f);
        PbrMats["Mat_FlowerYellow"] = PbrMat("Mat_FlowerYellow", new Color(0.96f, 0.78f, 0.18f), 0.48f, 0f);
        PbrMats["Mat_FlowerPurple"] = PbrMat("Mat_FlowerPurple", new Color(0.65f, 0.36f, 0.82f), 0.48f, 0f);
        PbrMats["Mat_FlowerPink"] = PbrMat("Mat_FlowerPink", new Color(0.95f, 0.56f, 0.68f), 0.48f, 0f);
        PbrMats["Mat_FlowerWhite"] = PbrMat("Mat_FlowerWhite", new Color(0.97f, 0.96f, 0.93f), 0.48f, 0f);
        PbrMats["Mat_TerracottaPot"] = PbrMat("Mat_TerracottaPot", new Color(0.76f, 0.42f, 0.28f), 0.38f, 0f);
        PbrMats["Mat_Water"] = PbrMat("Mat_Water", new Color(0.14f, 0.44f, 0.58f), 0.94f, 0.15f, null, "Water_Normal.png", 1.1f, 6f);
        PbrMats["Mat_ShellPearl"] = PbrMat("Mat_ShellPearl", new Color(0.96f, 0.86f, 0.82f), 0.78f, 0.12f);
        PbrMats["Mat_MushroomCap"] = PbrMat("Mat_MushroomCap", new Color(0.82f, 0.26f, 0.20f), 0.52f, 0f);
        PbrMats["Mat_MushroomStem"] = PbrMat("Mat_MushroomStem", new Color(0.92f, 0.88f, 0.78f), 0.35f, 0f);

        // 캐릭터 재질 (한수 & 다래)
        PbrMats["Mat_Character_Hansu_Skin"] = PbrMat("Mat_Character_Hansu_Skin", new Color(0.86f, 0.68f, 0.56f), 0.45f, 0f);
        PbrMats["Mat_Character_Hansu_Hair"] = PbrMat("Mat_Character_Hansu_Hair", new Color(0.22f, 0.23f, 0.25f), 0.40f, 0f);
        PbrMats["Mat_Character_Hansu_Top"] = PbrMat("Mat_Character_Hansu_Top", new Color(0.22f, 0.33f, 0.46f), 0.30f, 0f);
        PbrMats["Mat_Character_Hansu_Outer"] = PbrMat("Mat_Character_Hansu_Outer", new Color(0.35f, 0.39f, 0.28f), 0.32f, 0f);
        PbrMats["Mat_Character_Hansu_Bottom"] = PbrMat("Mat_Character_Hansu_Bottom", new Color(0.18f, 0.20f, 0.24f), 0.28f, 0f);
        PbrMats["Mat_Character_Hansu_Shoes"] = PbrMat("Mat_Character_Hansu_Shoes", new Color(0.18f, 0.14f, 0.11f), 0.48f, 0f);
        PbrMats["Mat_Character_Hansu_EyeDark"] = PbrMat("Mat_Character_Hansu_EyeDark", new Color(0.06f, 0.05f, 0.04f), 0.92f, 0f);
        PbrMats["Mat_Character_Hansu_EyeWhite"] = PbrMat("Mat_Character_Hansu_EyeWhite", new Color(0.97f, 0.97f, 0.98f), 0.88f, 0f);
        PbrMats["Mat_Character_Hansu_Lip"] = PbrMat("Mat_Character_Hansu_Lip", new Color(0.72f, 0.48f, 0.42f), 0.50f, 0f);

        // 다래: 애니메이션풍 평면 색(텍스처 없음, 낮은 광택) + 반전 껍질 외곽선. 값은 tools/build_inzoi_assets.py와 같게 유지.
        // 다래 텍스처는 tools/paint_darae_textures.py가 색까지 칠해 만든다. 색이 두 번 곱해지지 않게 틴트는 흰색(신발만 어둡게).
        // 타일링·노멀 세기는 tools/preview_darae_textures.py의 값과 같다.
        PbrMats["Mat_Character_Darae_Skin"] = PbrMat("Mat_Character_Darae_Skin", Color.white, 0.20f, 0f, "Darae_Skin_Albedo.png");
        PbrMats["Mat_Character_Darae_Face"] = PbrMat("Mat_Character_Darae_Face", Color.white, 0.20f, 0f, "Darae_Face_Albedo.png", null, 1f, 1f, null, false);
        PbrMats["Mat_Character_Darae_Hair"] = PbrMat("Mat_Character_Darae_Hair", Color.white, 0.25f, 0f, "Darae_Hair_Albedo.png", "Darae_Hair_Normal.png", 0.24f, 5f, null, true, 0.76f);
        PbrMats["Mat_Character_Darae_Top"] = PbrMat("Mat_Character_Darae_Top", Color.white, 0.10f, 0f, "Darae_Cotton_Albedo.png", "Darae_Cotton_Normal.png", 0.22f, 3f);
        PbrMats["Mat_Character_Darae_Outer"] = PbrMat("Mat_Character_Darae_Outer", Color.white, 0.10f, 0f, "Darae_Knit_Albedo.png", "Darae_Knit_Normal.png", 0.40f, 7f);
        PbrMats["Mat_Character_Darae_Bottom"] = PbrMat("Mat_Character_Darae_Bottom", Color.white, 0.10f, 0f, "Darae_Linen_Albedo.png", "Darae_Linen_Normal.png", 0.24f, 5f);
        PbrMats["Mat_Character_Darae_Apron"] = PbrMat("Mat_Character_Darae_Apron", Color.white, 0.10f, 0f, "Darae_Apron_Albedo.png", "Darae_Apron_Normal.png", 0.29f, 2.5f);
        PbrMats["Mat_Character_Darae_Belt"] = PbrMat("Mat_Character_Darae_Belt", Color.white, 0.30f, 0f, "Darae_Leather_Albedo.png", "Darae_Leather_Normal.png", 0.38f, 4f);
        PbrMats["Mat_Character_Darae_Shoes"] = PbrMat("Mat_Character_Darae_Shoes", new Color(0.73f, 0.72f, 0.82f), 0.30f, 0f, "Darae_Leather_Albedo.png", "Darae_Leather_Normal.png", 0.38f, 3f);
        PbrMats["Mat_Character_Darae_Eye"] = PbrMat("Mat_Character_Darae_Eye", Color.white, 0.40f, 0f, "Darae_EyeAtlas_Albedo.png", null, 1f, 1f, null, false);
        PbrMats["Mat_Character_Darae_EyeDark"] = PbrMat("Mat_Character_Darae_EyeDark", new Color(0.12f, 0.07f, 0.06f), 0.40f, 0f);
        PbrMats["Mat_Character_Darae_EyeWhite"] = PbrMat("Mat_Character_Darae_EyeWhite", new Color(1.00f, 1.00f, 1.00f), 0.40f, 0f);
        PbrMats["Mat_Character_Darae_Lip"] = PbrMat("Mat_Character_Darae_Lip", new Color(0.86f, 0.42f, 0.40f), 0.20f, 0f);
        PbrMats["Mat_Character_Darae_Kraft"] = PbrMat("Mat_Character_Darae_Kraft", Color.white, 0.10f, 0f, "Darae_Kraft_Albedo.png", "Darae_Kraft_Normal.png", 0.42f, 1.25f);
        PbrMats["Mat_Character_Darae_Outline"] = PbrMat("Mat_Character_Darae_Outline", new Color(0.19f, 0.11f, 0.08f), 0f, 0f);
    }

    static Texture2D LoadTex(string file, bool isNormal, bool repeat = true)
    {
        string path = BlenderTextures + file;
        var imp = AssetImporter.GetAtPath(path) as TextureImporter;
        if (imp != null)
        {
            bool dirty = false;
            var targetType = isNormal ? TextureImporterType.NormalMap : TextureImporterType.Default;
            var targetWrap = repeat ? TextureWrapMode.Repeat : TextureWrapMode.Clamp;
            if (imp.textureType != targetType) { imp.textureType = targetType; dirty = true; }
            if (imp.wrapMode != targetWrap) { imp.wrapMode = targetWrap; dirty = true; }
            if (imp.anisoLevel != 8) { imp.anisoLevel = 8; dirty = true; }
            if (dirty) imp.SaveAndReimport();
        }
        return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
    }

    static Material PbrMat(string name, Color color, float smoothness, float metallic,
        string albedoFile = null, string normalFile = null, float bumpScale = 1f, float tiling = 1f, Color? emission = null,
        bool repeat = true, float tilingY = 0f)
    {
        var mat = Mat(name, color);
        mat.SetFloat("_Smoothness", smoothness);
        mat.SetFloat("_Metallic", metallic);
        var scale = new Vector2(tiling, tilingY > 0f ? tilingY : tiling);
        mat.mainTextureScale = scale;
        mat.SetTextureScale("_BaseMap", scale);
        if (albedoFile != null)
        {
            var tex = LoadTex(albedoFile, false, repeat);
            mat.SetTexture("_BaseMap", tex);
            mat.mainTexture = tex;
        }
        else mat.SetTexture("_BaseMap", null); // 이미 있는 .mat에 남은 예전 텍스처를 지운다
        if (normalFile != null)
        {
            var norm = LoadTex(normalFile, true);
            mat.SetTexture("_BumpMap", norm);
            mat.SetTextureScale("_BumpMap", scale);
            mat.SetFloat("_BumpScale", bumpScale);
            mat.EnableKeyword("_NORMALMAP");
        }
        else
        {
            mat.SetTexture("_BumpMap", null);
            mat.DisableKeyword("_NORMALMAP");
        }
        if (emission.HasValue)
        {
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", emission.Value);
        }
        EditorUtility.SetDirty(mat);
        return mat;
    }

    static void ApplyPbrMaterials(GameObject go)
    {
        foreach (var r in go.GetComponentsInChildren<Renderer>())
        {
            var mats = r.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
            {
                if (mats[i] == null) continue;
                string key = mats[i].name.Split(' ')[0];
                if (PbrMats.TryGetValue(key, out var pbr)) mats[i] = pbr;
            }
            r.sharedMaterials = mats;
        }
    }

    // 이동과 충돌 확인: 열린 방향으로는 움직이고, 건물 쪽으로는 벽 앞에서 멈춰야 한다.
    static void SelfCheck(PlayerController player, Bounds northHouse)
    {
        Physics.SyncTransforms();
        var start = player.transform.position;

        for (int i = 0; i < 50; i++) player.Step(Vector2.left, 0.02f);
        float x = player.transform.position.x;
        if (x > -4f) throw new System.Exception($"자가 점검 실패: 서쪽으로 이동하지 않음 (x={x})");

        Teleport(player, start);
        for (int i = 0; i < 200; i++) player.Step(Vector2.up, 0.02f);
        float z = player.transform.position.z, wall = northHouse.min.z;
        if (z < wall - 1.5f || z > wall) throw new System.Exception($"자가 점검 실패: 북쪽 집 앞에서 멈추지 않음 (z={z}, 벽={wall})");

        Debug.Log($"VillageBuilder 자가 점검: 서쪽 이동 x={x:F2}, 북쪽 집 앞 정지 z={z:F2} (벽 z={wall:F2})");
        Teleport(player, start);
        player.transform.rotation = Quaternion.identity;

        // LLM 응답 검사: 올바른 응답만 통과하고 나머지는 대체 대사로 가야 한다.
        if (!DialogueManager.TryParse("{\"line\":\"안녕\",\"expression\":\"happy\"}", out string line, out int expr)
            || line != "안녕" || expr != 1
            || DialogueManager.TryParse(null, out _, out _)
            || DialogueManager.TryParse("JSON 아님", out _, out _)
            || DialogueManager.TryParse("{\"line\":\"\",\"expression\":\"happy\"}", out _, out _)
            || DialogueManager.TryParse("{\"line\":\"버섯은 상还不错해\",\"expression\":\"happy\"}", out _, out _)
            || DialogueManager.TryParse("{\"line\":\"장미 한 бук을 드렸죠\",\"expression\":\"happy\"}", out _, out _)
            || DialogueManager.TryParse("{\"line\":\"안녕\",\"expression\":\"sleepy\"}", out _, out _))
            throw new System.Exception("자가 점검 실패: LLM 응답 검사");
    }

    // 선물 규칙과 저장 확인(임시 파일 사용): 싫어하는 꽃 -1, 좋아하는 조개 +2, 없는 물건은 줄 수 없고, 다시 읽어도 같아야 한다.
    static void GiftCheck(Npc fisher)
    {
        GameState.PathOverride = "Temp/selfcheck-save.json";
        File.Delete(GameState.PathOverride);
        GameState.Reset();
        try
        {
            GameState.Add("flower", 1);
            GameState.Add("shell", 1);
            bool ok = GameState.Gift(fisher, "flower") != null && GameState.Of(fisher.id).affinity == -1
                && GameState.Gift(fisher, "flower") == null && GameState.Of(fisher.id).affinity == -1
                && GameState.Gift(fisher, "shell") != null && GameState.Of(fisher.id).affinity == 1;
            GameState.Reset(); // 파일에서 다시 읽는다
            var state = GameState.Of(fisher.id);
            ok = ok && state.affinity == 1 && state.memories.Count == 2
                && GameState.Count("flower") == 0 && GameState.Count("shell") == 0
                && fisher.SystemPrompt().Contains("조개 1개를 선물했다");
            if (!ok) throw new System.Exception("자가 점검 실패: 선물·저장");

            // 조건 전환: 일반은 성격과 기억이 없고, 성격은 기억만 없어야 한다.
            global::Npc.condition = global::Npc.Condition.Plain;
            string plain = fisher.SystemPrompt();
            global::Npc.condition = global::Npc.Condition.Persona;
            string persona = fisher.SystemPrompt();
            // "자네"는 성격 시트에만 나오는 말이다
            if (plain.Contains(fisher.displayName) || plain.Contains("[기억]") || plain.Contains("자네")
                || !persona.Contains(fisher.displayName) || persona.Contains("[기억]") || !persona.Contains("자네"))
                throw new System.Exception("자가 점검 실패: 조건 전환");
        }
        finally
        {
            GameState.PathOverride = null;
            GameState.Reset();
            global::Npc.condition = global::Npc.Condition.PersonaMemory;
        }
    }

    static void Pickup(GameObject go, string item)
    {
        go.name = "Pickup_" + item;
        go.AddComponent<Pickup>().itemId = item;
    }

    // 제자리에 서서 마을 가운데를 보는 주민. 실사 인체 비율(1.75m)로 배치해 1인칭 눈높이(1.56m)와 자연스럽게 맞춘다.
    static Npc Npc(string model, Vector3 pos, RuntimeAnimatorController idle)
    {
        var go = Model(BlenderModels + model + ".fbx", "Npc", pos, 0f, 1.75f, false);
        go.transform.rotation = Quaternion.LookRotation(-pos);
        if (!go.TryGetComponent<Animator>(out var animator)) animator = go.AddComponent<Animator>();
        animator.runtimeAnimatorController = idle;
        animator.applyRootMotion = false;
        var body = go.AddComponent<CapsuleCollider>();
        float s = go.transform.localScale.y;
        body.radius = 0.38f / s;
        body.height = 1.75f / s;
        body.center = Vector3.up * 0.88f / s;
        return go.AddComponent<Npc>();
    }

    static void Teleport(PlayerController player, Vector3 pos)
    {
        var cc = player.GetComponent<CharacterController>();
        cc.enabled = false;
        player.transform.position = pos;
        cc.enabled = true;
        Physics.SyncTransforms();
    }

    static GameObject Building(string name, string model, Vector3 pos, float yaw)
    {
        var go = Model(BlenderModels + model + ".fbx", name, pos, yaw, 9f, true);
        var b = Bounds(go);
        var box = go.AddComponent<BoxCollider>();
        box.center = go.transform.InverseTransformPoint(b.center);
        var size = go.transform.InverseTransformVector(b.size);
        box.size = new Vector3(Mathf.Abs(size.x), Mathf.Abs(size.y), Mathf.Abs(size.z));
        return go;
    }

    static GameObject InstantiateRaw(string path, string name, Vector3 pos, float yaw)
    {
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
        if (prefab == null) throw new System.Exception("모델 없음: " + path);
        var go = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
        go.name = name;
        go.transform.SetPositionAndRotation(pos, Quaternion.Euler(0f, yaw, 0f));
        return go;
    }

    // 모델을 놓고, 높이(또는 가로 폭)가 size가 되도록 크기를 맞춘 뒤 바닥을 y=0에 붙인다.
    static GameObject Model(string path, string name, Vector3 pos, float yaw, float size, bool byWidth)
    {
        var go = InstantiateRaw(path, name, pos, yaw);
        ApplyPbrMaterials(go);
        var b = Bounds(go);
        go.transform.localScale *= size / (byWidth ? Mathf.Max(b.size.x, b.size.z) : b.size.y);
        go.transform.position += Vector3.up * (pos.y - Bounds(go).min.y);
        return go;
    }

    static Bounds Bounds(GameObject go)
    {
        var renderers = go.GetComponentsInChildren<Renderer>();
        var b = renderers[0].bounds;
        foreach (var r in renderers) b.Encapsulate(r.bounds);
        return b;
    }

    static AnimatorController CharacterAnimator(string fbxPath, string controllerPath)
    {
        var importer = (ModelImporter)AssetImporter.GetAtPath(fbxPath);
        importer.animationType = ModelImporterAnimationType.Generic;
        var clips = importer.defaultClipAnimations;
        foreach (var c in clips) c.loopTime = c.name.EndsWith("idle") || c.name.EndsWith("walk");
        importer.clipAnimations = clips;
        importer.SaveAndReimport();
        var all = AssetDatabase.LoadAllAssetsAtPath(fbxPath).OfType<AnimationClip>()
            .Where(c => !c.name.StartsWith("__preview__")).ToArray();
        var idleClip = all.First(c => c.name.EndsWith("idle"));
        var walkClip = all.First(c => c.name.EndsWith("walk"));

        Directory.CreateDirectory("Assets/Animations");
        AssetDatabase.DeleteAsset(controllerPath);
        var ctrl = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);
        ctrl.AddParameter("Speed", AnimatorControllerParameterType.Float);
        var sm = ctrl.layers[0].stateMachine;
        var idle = sm.AddState("Idle");
        idle.motion = idleClip;
        var walk = sm.AddState("Walk");
        walk.motion = walkClip;
        Transition(idle, walk, AnimatorConditionMode.Greater);
        Transition(walk, idle, AnimatorConditionMode.Less);
        return ctrl;
    }

    static void Transition(AnimatorState from, AnimatorState to, AnimatorConditionMode mode)
    {
        var t = from.AddTransition(to);
        t.hasExitTime = false;
        t.duration = 0.1f;
        t.AddCondition(mode, 0.1f, "Speed");
    }

    static Material Mat(string name, Color color, string shader = "Universal Render Pipeline/Lit")
    {
        Directory.CreateDirectory("Assets/Materials");
        string path = $"Assets/Materials/{name}.mat";
        var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (mat == null)
        {
            mat = new Material(Shader.Find(shader));
            AssetDatabase.CreateAsset(mat, path);
        }
        else
        {
            mat.shader = Shader.Find(shader);
        }
        mat.SetColor("_BaseColor", color);
        mat.SetColor("_Color", color);
        return mat;
    }

    // 눈으로 확인할 미리보기 이미지 (Logs/*.png, git 제외)
    static void Screenshot(Camera cam, string outPath)
    {
        var rt = new RenderTexture(1280, 720, 24);
        cam.targetTexture = rt;
        cam.Render(); // 첫 렌더에서 SRP 상수 버퍼와 텍스처 업로드를 워밍업
        cam.Render();
        RenderTexture.active = rt;
        var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
        cam.targetTexture = null;
        RenderTexture.active = null;
        Directory.CreateDirectory("Logs");
        File.WriteAllBytes(outPath, tex.EncodeToPNG());
    }
}
