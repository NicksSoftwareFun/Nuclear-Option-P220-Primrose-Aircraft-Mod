using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

// Builds P220Primrose.prefab from a pristine copy of the EW-25 Medusa plus the P220 art (P220_parts.fbx + P220_layout.json),
// and the mod's own def, parameters, hangar op and weapon mounts. Run from the menu (P220 > Rebuild) or P220Builder.Build().
// Every value is a literal on purpose.
public static class P220Builder
{
    const string MOD = "Assets/Blueprinter/Mods/P220Primrose/";
    const string ART = MOD + "Art/";
    const string MNT = MOD + "Mounts/";
    const string TOOLS = "Assets/P220Tools/";
    const string SRC = TOOLS + "P220_ew1src.prefab";
    const string DST = MOD + "P220Primrose.prefab";
    const string DEF = MOD + "P220Primrose_def.asset";
    const string PAR = MOD + "P220Primrose_Parameters.asset";
    const string PH = "Assets/Blueprinter/_donotship/";
    const string EW1 = PH + "GameObject/EW1_PLACEHOLDER.prefab";

    [System.Serializable] class E { public string name, coll, kind; public float[] pos, rot, bmin, bmax; public string[] mats; }
    [System.Serializable] class W { public E[] items; }
    [System.Serializable] class PieceE { public string name; public string of; public string[] touch; }
    [System.Serializable] class PW { public PieceE[] items; }
    static List<PieceE> PIECES = new List<PieceE>();

    static Dictionary<string, E> L;
    static Dictionary<string, Mesh> M;
    static Dictionary<string, Material> MAT;
    static Transform root;
    static StringBuilder log;
    static readonly HashSet<Object> doomed = new HashSet<Object>();
    static readonly List<GameObject> doomedRoots = new List<GameObject>();
    static readonly List<Component> doomedComps = new List<Component>();

    [MenuItem("P220/Rebuild")]
    public static void Menu() { Debug.Log(Build()); }

    // ------------------------------------------------------------------ helpers
    static readonly Quaternion LaserRest = Quaternion.LookRotation(Vector3.down, Vector3.back);
    static Vector3 BtoU(float[] p) { return new Vector3(p[0], p[2], p[1]); }
    static Vector3 P(string n) { return BtoU(Lget(n).pos); }
    static E Lget(string n) { E e; if (!L.TryGetValue(n, out e)) throw new System.Exception("layout missing " + n); return e; }
    static Transform Find(Transform under, string name)
    {
        if (under.name == name) return under;
        foreach (Transform c in under) { var r = Find(c, name); if (r != null) return r; }
        return null;
    }
    static Transform Need(string name)
    {
        var t = Find(root, name);
        if (t == null) throw new System.Exception("missing " + name);
        return t;
    }
    static Transform New(string name, Transform parent)
    {
        var go = new GameObject(name); go.transform.SetParent(parent, false); return go.transform;
    }
    static Component C(Transform t, string type) { return t.GetComponents<Component>().FirstOrDefault(c => c != null && c.GetType().Name == type); }
    static Material[] Mats(string mesh) { return Lget(mesh).mats.Select(m => MAT[m]).ToArray(); }
    static void SetMesh(Transform t, string mesh)
    {
        var mf = t.GetComponent<MeshFilter>(); if (mf == null) mf = t.gameObject.AddComponent<MeshFilter>();
        mf.sharedMesh = M[mesh];
        var mr = t.GetComponent<MeshRenderer>(); if (mr == null) mr = t.gameObject.AddComponent<MeshRenderer>();
        mr.sharedMaterials = Mats(mesh);
    }
    static void NoMesh(Transform t) { var mf = t.GetComponent<MeshFilter>(); if (mf != null) mf.sharedMesh = null; }
    static void SetCol(Transform t, string col)
    {
        var mc = t.GetComponent<MeshCollider>(); if (mc == null) mc = t.gameObject.AddComponent<MeshCollider>();
        mc.convex = true; mc.sharedMesh = M[col];
    }
    static void Lod(Transform t, string col)
    {
        var l = t.Find(t.name + "_lod1");
        if (l == null) return;
        l.localPosition = Vector3.zero; l.localRotation = Quaternion.identity; l.localScale = Vector3.one;
        var mf = l.GetComponent<MeshFilter>(); if (mf != null) mf.sharedMesh = M[col];
    }
    // a whole part: pivot from the layout (world-aligned), visible mesh, convex hull collider, LOD shell
    static Transform PartAt(string name, string mesh = null)
    {
        mesh = mesh ?? name;
        var t = Need(name);
        t.position = P(mesh); t.rotation = Quaternion.identity;
        SetMesh(t, mesh); SetCol(t, mesh + "_colmesh"); Lod(t, mesh + "_colmesh");
        return t;
    }
    static void Doom(Transform t)
    {
        if (t == null) return;
        doomedRoots.Add(t.gameObject);
        foreach (var tr in t.GetComponentsInChildren<Transform>(true))
        {
            doomed.Add(tr.gameObject);
            foreach (var c in tr.GetComponents<Component>()) if (c != null) doomed.Add(c);
        }
    }
    static void DoomName(string n) { Doom(Find(root, n)); }
    static void DoomComp(Component c) { if (c == null) return; doomed.Add(c); doomedComps.Add(c); }
    // remove every reference to a doomed object: the innermost array element holding it goes, a plain field is nulled
    static void Purge()
    {
        foreach (var c in root.GetComponentsInChildren<Component>(true))
        {
            if (c == null || doomed.Contains(c) || c is Transform) continue;
            var so = new SerializedObject(c);
            var it = so.GetIterator();
            var hits = new List<string>();
            while (it.Next(true))
                if (it.propertyType == SerializedPropertyType.ObjectReference && it.objectReferenceValue != null && doomed.Contains(it.objectReferenceValue))
                    hits.Add(it.propertyPath);
            if (hits.Count == 0) continue;
            var dels = new List<KeyValuePair<string, int>>();
            foreach (var h in hits)
            {
                int k = h.LastIndexOf(".Array.data[");
                if (k < 0) { so.FindProperty(h).objectReferenceValue = null; log.AppendLine("null " + c.name + "." + c.GetType().Name + "." + h); continue; }
                int e = h.IndexOf(']', k);
                dels.Add(new KeyValuePair<string, int>(h.Substring(0, k), int.Parse(h.Substring(k + 12, e - k - 12))));
            }
            foreach (var d in dels.Distinct().OrderByDescending(x => x.Value))
            {
                var arr = so.FindProperty(d.Key);
                if (arr == null || !arr.isArray || d.Value >= arr.arraySize) continue;   // its parent element already went
                int before = arr.arraySize;
                arr.DeleteArrayElementAtIndex(d.Value);
                if (arr.arraySize == before) arr.DeleteArrayElementAtIndex(d.Value);
                log.AppendLine("drop " + c.name + "." + c.GetType().Name + "." + d.Key + "[" + d.Value + "]");
            }
            so.ApplyModifiedPropertiesWithoutUndo();
        }
        foreach (var c in doomedComps) if (c != null) Object.DestroyImmediate(c);
        foreach (var g in doomedRoots) if (g != null) Object.DestroyImmediate(g);
        doomed.Clear(); doomedRoots.Clear(); doomedComps.Clear();
    }
    static SerializedProperty Prop(SerializedObject so, string path)
    {
        var p = so.FindProperty(path);
        if (p == null) log.AppendLine("MISSING PROP " + so.targetObject.GetType().Name + "." + path);
        return p;
    }
    static void Set(Object c, string path, object v)
    {
        if (c == null) { log.AppendLine("NULL TARGET for " + path); return; }
        var so = new SerializedObject(c);
        var p = Prop(so, path);
        if (p == null) return;
        if (v is float) { if (p.propertyType == SerializedPropertyType.Integer) p.intValue = (int)(float)v; else p.floatValue = (float)v; }
        else if (v is int) { if (p.propertyType == SerializedPropertyType.Float) p.floatValue = (int)v; else p.intValue = (int)v; }
        else if (v is bool) p.boolValue = (bool)v;
        else if (v is Vector3) p.vector3Value = (Vector3)v;
        else if (v is string) p.stringValue = (string)v;
        else if (v is AnimationCurve) p.animationCurveValue = (AnimationCurve)v;
        else if (v == null || v is Object) p.objectReferenceValue = (Object)v;
        else log.AppendLine("UNSUPPORTED " + path);
        so.ApplyModifiedPropertiesWithoutUndo();
    }
    static Object Get(Object c, string path)
    {
        if (c == null) return null;
        var p = Prop(new SerializedObject(c), path); return p != null ? p.objectReferenceValue : null;
    }
    static void Size(Object c, string path, int n)
    {
        var so = new SerializedObject(c); var p = Prop(so, path); if (p == null) return;
        p.arraySize = n; so.ApplyModifiedPropertiesWithoutUndo();
    }
    static void ObjArray(Object c, string path, params Object[] items)
    {
        var so = new SerializedObject(c); var p = Prop(so, path); if (p == null) return;
        p.arraySize = items.Length;
        for (int i = 0; i < items.Length; i++) p.GetArrayElementAtIndex(i).objectReferenceValue = items[i];
        so.ApplyModifiedPropertiesWithoutUndo();
    }
    static Component AP(string n) { return C(Need(n), "AeroPart"); }
    static int jointIterations = 6;
    static void Joints(string part, params object[] pairs)
    {
        var ap = AP(part);
        int n = pairs.Length / 2;
        Size(ap, "joints", n);
        for (int i = 0; i < n; i++)
        {
            string j = "joints.Array.data[" + i + "].";
            Set(ap, j + "connectedPart", AP((string)pairs[2 * i]));
            Set(ap, j + "tensor", null);
            Set(ap, j + "anchor", null);
            Set(ap, j + "breakForce", (float)pairs[2 * i + 1]);
            Set(ap, j + "breakTorque", (float)pairs[2 * i + 1]);
            Set(ap, j + "solverIterations", jointIterations);
        }
    }
    // ------------------------------------------------------------------ livery (0.3.27): the stock aircraft skin shader
    // P220_skin uses the game's AircraftSkin shader graph like every stock airframe: painted base colour, normal,
    // metallic/smoothness, AO, and the damage colour/normal whose alpha opens the torn-panel holes as _HitPoints falls.
    // The textures come from art/scripts/liv (p220_paint.py, p220_dmg_alpha.py, p220_bake_ao.py) into Art/Skin.
    const string SKIN = ART + "Skin/";
    public const string LIVERY = ART + "P220_livery_plink.asset";
    static Texture2D SkinTex(string name, bool srgb, bool normal, bool alpha) { return SkinTex(name, srgb, normal, alpha, false); }
    static Texture2D SkinTex(string name, bool srgb, bool normal, bool alpha, bool tile)
    {
        string path = SKIN + name + ".png";
        var ti = (TextureImporter)AssetImporter.GetAtPath(path);
        if (ti == null) throw new System.Exception("missing " + path);
        ti.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
        ti.sRGBTexture = srgb;
        ti.alphaSource = alpha ? TextureImporterAlphaSource.FromInput : TextureImporterAlphaSource.None;
        ti.alphaIsTransparency = false; ti.mipmapEnabled = true; ti.maxTextureSize = 2048;
        ti.textureCompression = TextureImporterCompression.CompressedHQ;
        ti.wrapMode = tile ? TextureWrapMode.Repeat : TextureWrapMode.Clamp; ti.anisoLevel = 4;
        if (tile) ti.maxTextureSize = 1024;
        ti.SaveAndReimport();
        return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
    }
    // 0.4.7 interior damage: the cargo bay / fuselage inner wall (P220_bay) and the cabin liner (P220_lining) use the
    // same AircraftSkin shader with their own tiling maps (art/scripts/liv/p220_interior_tex.py, 2.5 m per tile), so they
    // soot, scorch and tear as their part loses health. They are never the first material of a renderer, so the game's
    // livery never reaches them; the plugin passes the part's health to them (P220Interior).
    static Material InteriorMat(string kind)
    {
        string k = "P220_" + kind;
        var b = SkinTex(k + "_b", true, false, false, true);
        var n = SkinTex(k + "_n", false, true, false, true);
        var m = SkinTex(k + "_m", false, false, true, true);
        var ao = SkinTex(k + "_ao", false, false, false, true);
        var db = SkinTex(k + "_dmg_b", true, false, true, true);
        var dn = SkinTex(k + "_dmg_n", false, true, false, true);
        var sh = AssetDatabase.LoadAssetAtPath<Shader>(PH + "Shader/Shader Graphs_AircraftSkin_PLACEHOLDER.shader");
        string path = ART + k + ".mat";
        var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (mat == null) { mat = new Material(sh); AssetDatabase.CreateAsset(mat, path); }
        mat.shader = sh; mat.shaderKeywords = new string[0]; mat.name = k;
        mat.SetTexture("_Basecolor", b); mat.SetTexture("_Normal", n); mat.SetTexture("_Metallic", m); mat.SetTexture("_AO", ao);
        mat.SetTexture("_BasecolorDmg", db); mat.SetTexture("_NormalDmg", dn); mat.SetTexture("_Livery", b);
        mat.SetFloat("_HitPoints", 100f); mat.SetFloat("_Glossiness", 0f);
        EditorUtility.SetDirty(mat);
        return mat;
    }
    static Material SkinMat()
    {
        var b = SkinTex("P220_skin_b", true, false, false);
        var n = SkinTex("P220_skin_n", false, true, false);
        var m = SkinTex("P220_skin_m", false, false, true);
        var ao = SkinTex("P220_skin_ao", false, false, false);
        var db = SkinTex("P220_skin_dmg_b", true, false, true);
        var dn = SkinTex("P220_skin_dmg_n", false, true, false);
        string path = ART + "P220_skin.mat";
        var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
        var sh = AssetDatabase.LoadAssetAtPath<Shader>(PH + "Shader/Shader Graphs_AircraftSkin_PLACEHOLDER.shader");
        if (sh == null) throw new System.Exception("AircraftSkin shader placeholder not found");
        if (mat == null) { mat = new Material(sh); AssetDatabase.CreateAsset(mat, path); }
        mat.shader = sh; mat.shaderKeywords = new string[0];
        mat.SetTexture("_Basecolor", b); mat.SetTexture("_Normal", n); mat.SetTexture("_Metallic", m); mat.SetTexture("_AO", ao);
        mat.SetTexture("_BasecolorDmg", db); mat.SetTexture("_NormalDmg", dn); mat.SetTexture("_Livery", b);
        mat.SetFloat("_HitPoints", 100f); mat.SetFloat("_Glossiness", 0f);
        EditorUtility.SetDirty(mat);
        // LiveryData for the house livery (liveries[0]); its texture replaces _Livery on the skin material in game
        var liv = AssetDatabase.LoadMainAssetAtPath(LIVERY) as ScriptableObject;
        if (liv == null)
        {
            var t = System.AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetType("LiveryData")).FirstOrDefault(x => x != null);
            if (t == null) throw new System.Exception("LiveryData type not found");
            liv = ScriptableObject.CreateInstance(t); AssetDatabase.CreateAsset(liv, LIVERY);
        }
        var so = new SerializedObject(liv);
        so.FindProperty("Texture").objectReferenceValue = b;
        so.FindProperty("Glossiness").floatValue = 0f;
        so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(liv);
        log.AppendLine("skin material + livery " + AssetDatabase.AssetPathToGUID(LIVERY));
        // 0.4.13 (the author 2026-11-08): two more liveries, each only its own colour texture like the stock liveries
        foreach (var k in new[] { "civil", "pala", "royal" })
        {
            var tb = SkinTex("P220_skin_" + k + "_b", true, false, false);
            string lp = ART + "P220_livery_" + k + ".asset";
            var l2 = AssetDatabase.LoadMainAssetAtPath(lp) as ScriptableObject;
            if (l2 == null) { l2 = ScriptableObject.CreateInstance(liv.GetType()); AssetDatabase.CreateAsset(l2, lp); }
            var s2 = new SerializedObject(l2);
            s2.FindProperty("Texture").objectReferenceValue = tb; s2.FindProperty("Glossiness").floatValue = 0f;
            s2.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(l2);
        }
        return mat;
    }
    static Material LitMat(string name, Color col, float smooth, float metal)
    {
        string path = ART + name + ".mat";
        var m = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (m == null)
        {
            m = new Material(AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/jet_mechanical_PLACEHOLDER.mat"));
            m.name = name;
            AssetDatabase.CreateAsset(m, path);
        }
        foreach (var t in new[] { "_BaseMap", "_MainTex", "_BumpMap", "_MetallicGlossMap", "_OcclusionMap", "_EmissionMap" })
            if (m.HasProperty(t)) m.SetTexture(t, null);
        m.SetColor("_BaseColor", col); if (m.HasProperty("_Color")) m.SetColor("_Color", col);
        m.SetFloat("_Smoothness", smooth); m.SetFloat("_Metallic", metal);
        EditorUtility.SetDirty(m);
        return m;
    }
    // 0.4.7 (textured grey plastic instead of flat grey): the moulded lining (consoles, knee bolster, walls, seat shells)
    // gets a fine leather-grain plastic (art: /tmp/ck220/plastic_tex.py). The lining UVs are box-projected at 2.5 m per unit,
    // so the tiling x5 makes one 0.5 m tile.
    static Material PlasticMat()
    {
        var m = LitMat("P220_cabin", Color.white, 0.22f, 0f);
        foreach (var n in new[] { "b", "n" })
        {
            var ti = (TextureImporter)AssetImporter.GetAtPath(ART + "P220_plastic_" + n + ".png");
            if (ti == null) { log.AppendLine("no P220_plastic_" + n + ".png, lining stays flat grey"); m.SetColor("_BaseColor", new Color32(150, 154, 158, 255)); return m; }
            ti.textureType = n == "n" ? TextureImporterType.NormalMap : TextureImporterType.Default; ti.sRGBTexture = n == "b";
            ti.wrapMode = TextureWrapMode.Repeat; ti.maxTextureSize = 1024; ti.mipmapEnabled = true; ti.anisoLevel = 4; ti.SaveAndReimport();
        }
        var b = AssetDatabase.LoadAssetAtPath<Texture2D>(ART + "P220_plastic_b.png");
        var nm = AssetDatabase.LoadAssetAtPath<Texture2D>(ART + "P220_plastic_n.png");
        foreach (var t in new[] { "_BaseMap", "_MainTex" }) if (m.HasProperty(t)) { m.SetTexture(t, b); m.SetTextureScale(t, new Vector2(5f, 5f)); }
        m.SetTexture("_BumpMap", nm); m.SetFloat("_BumpScale", 1f); m.EnableKeyword("_NORMALMAP");
        EditorUtility.SetDirty(m);
        return m;
    }
    static string Placeholder(string name, string type)
    {
        foreach (var g in AssetDatabase.FindAssets(name + "_PLACEHOLDER t:" + type))
        {
            var p = AssetDatabase.GUIDToAssetPath(g);
            if (System.IO.Path.GetFileNameWithoutExtension(p) == name + "_PLACEHOLDER" && !p.Contains("__dedupe")) return p;
        }
        foreach (var g in AssetDatabase.FindAssets(name + "_PLACEHOLDER t:" + type))
        {
            var p = AssetDatabase.GUIDToAssetPath(g);
            if (System.IO.Path.GetFileNameWithoutExtension(p) == name + "_PLACEHOLDER") return p;
        }
        throw new System.Exception("no placeholder " + name + " (" + type + ")");
    }
    static Object Mount(string name)
    {
        var custom = AssetDatabase.LoadMainAssetAtPath(MNT + name + ".asset");
        if (custom != null) return custom;
        return AssetDatabase.LoadMainAssetAtPath(Placeholder(name, "WeaponMount"));
    }

    // ------------------------------------------------------------------ setup: pristine donor, def, parameters, importer
    static void Setup()
    {
        if (!AssetDatabase.IsValidFolder("Assets/P220Tools")) AssetDatabase.CreateFolder("Assets", "P220Tools");
        if (!AssetDatabase.IsValidFolder(MOD + "Mounts")) AssetDatabase.CreateFolder(MOD.TrimEnd('/'), "Mounts");
        if (AssetDatabase.LoadAssetAtPath<GameObject>(SRC) == null)
        {
            if (!AssetDatabase.CopyAsset(EW1, SRC)) throw new System.Exception("copy of the Medusa prefab failed");
            log.AppendLine("saved pristine Medusa copy to " + SRC);
        }
        if (AssetDatabase.LoadMainAssetAtPath(DEF) == null)
        {
            if (!AssetDatabase.CopyAsset(PH + "MonoBehaviour/EW1_PLACEHOLDER.asset", DEF)) throw new System.Exception("def copy failed");
            log.AppendLine("copied Medusa definition");
        }
        if (AssetDatabase.LoadMainAssetAtPath(PAR) == null)
        {
            if (!AssetDatabase.CopyAsset(PH + "MonoBehaviour/EW1Parameters_PLACEHOLDER.asset", PAR)) throw new System.Exception("parameters copy failed");
            log.AppendLine("copied Medusa parameters");
        }
        var imp = (ModelImporter)AssetImporter.GetAtPath(ART + "P220_parts.fbx");
        if (imp.materialImportMode != ModelImporterMaterialImportMode.None || !imp.isReadable || imp.animationType != ModelImporterAnimationType.None)
        {
            imp.materialImportMode = ModelImporterMaterialImportMode.None; imp.isReadable = true; imp.importAnimation = false;
            imp.animationType = ModelImporterAnimationType.None; imp.importCameras = false; imp.importLights = false;
            imp.meshCompression = ModelImporterMeshCompression.Off; imp.weldVertices = true;
            imp.SaveAndReimport();
            log.AppendLine("fbx importer set");
        }
    }

    // ------------------------------------------------------------------ build
    public static string Build()
    {
        log = new StringBuilder();
        try { Setup(); } catch (System.Exception ex) { return log + "SETUP ERROR " + ex; }
        L = JsonUtility.FromJson<W>("{\"items\":" + System.IO.File.ReadAllText(ART + "P220_layout.json") + "}").items.ToDictionary(e => e.name);
        M = new Dictionary<string, Mesh>();
        foreach (var o in AssetDatabase.LoadAllAssetsAtPath(ART + "P220_parts.fbx")) if (o is Mesh) M[o.name] = (Mesh)o;
        MAT = new Dictionary<string, Material>();
        MAT["P220_skin"] = SkinMat();
        MAT["P220_dark"] = LitMat("P220_dark", new Color32(22, 24, 28, 255), 0.75f, 0f);
        MAT["P220_metal"] = LitMat("P220_metal", new Color32(105, 108, 112, 255), 0.35f, 0.4f);
        MAT["P220_tyre"] = LitMat("P220_tyre", new Color32(16, 16, 16, 255), 0.15f, 0f);
        MAT["P220_window"] = LitMat("P220_window", new Color32(18, 21, 26, 255), 0.85f, 0f);
        MAT["P220_bay"] = InteriorMat("bay");
        // internal structure (0.3.25): the game's own shared structure materials, as on every stock aircraft and the PB-22
        // (frames, spars, ribs and the engine cores: jet_mechanical; floor beams, centre box skins, bulkhead stiffeners: aircraft_structure)
        var jm = AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/jet_mechanical_PLACEHOLDER.mat");
        var asm = AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/aircraft_structure_PLACEHOLDER.mat");
        MAT["P220_mech"] = jm != null ? jm : MAT["P220_metal"];
        MAT["P220_struct"] = asm != null ? asm : MAT["P220_bay"];
        if (jm == null || asm == null) log.AppendLine("structure placeholder material missing");
        // the trainer's canopy glass: untextured, nearly clear (the Medusa canopy texture gave the windows a gold tint)
        var glass = AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/trainer_glass_PLACEHOLDER.mat");
        MAT["P220_glass"] = glass != null ? glass : MAT["P220_dark"];
        var gint = AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/trainer_glass_int_PLACEHOLDER.mat");
        MAT["P220_glass_int"] = gint != null ? gint : MAT["P220_glass"];
        if (glass == null) log.AppendLine("trainer_glass_PLACEHOLDER not found, windshield is dark paint");
        // 0.3.29: fan parts. White spinner tip and spiral; the blurred fan disc uses the stock ducted-fan blur material
        MAT["P220_white"] = LitMat("P220_white", new Color32(232, 234, 232, 255), 0.75f, 0f);
        // 0.3.29 crew cabin fit: light grey lining (bins, dado, lavatory, cabinet, desks) and blue-grey seat fabric
        MAT["P220_lining"] = InteriorMat("lining");
        MAT["P220_seat"] = LitMat("P220_seat", new Color32(44, 52, 66, 255), 0.15f, 0f);
        var blur = AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/UtilityHelo1_fan_blur_PLACEHOLDER.mat");
        // 0.3.30 (wanted a better spinning fan): own blur disc texture (art/scripts/fanblur_tex.py) on a copy of
        // the stock ducted-fan blur material, nearly opaque so the core and mounts no longer show through a running fan
        MAT["P220_fanblur"] = MAT["P220_dark"];
        if (blur != null)
        {
            string tp = ART + "P220_fanblur.png";
            var ti = (TextureImporter)AssetImporter.GetAtPath(tp);
            if (ti != null)
            {
                ti.textureType = TextureImporterType.Default; ti.sRGBTexture = true; ti.alphaSource = TextureImporterAlphaSource.FromInput;
                ti.alphaIsTransparency = true; ti.mipmapEnabled = true; ti.wrapMode = TextureWrapMode.Clamp; ti.SaveAndReimport();
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(tp);
                string mp = ART + "P220_fanblur.mat";
                var mb = AssetDatabase.LoadAssetAtPath<Material>(mp);
                if (mb == null) { mb = new Material(blur); mb.name = "P220_fanblur"; AssetDatabase.CreateAsset(mb, mp); }
                else mb.CopyPropertiesFromMaterial(blur);
                foreach (var t in new[] { "_BaseMap", "_MainTex" }) if (mb.HasProperty(t)) mb.SetTexture(t, tex);
                if (mb.HasProperty("_BaseColor")) mb.SetColor("_BaseColor", Color.white);
                if (mb.HasProperty("_Color")) mb.SetColor("_Color", Color.white);
                EditorUtility.SetDirty(mb);
                MAT["P220_fanblur"] = mb;
            }
            else { log.AppendLine("no fan blur texture, stock blur used"); MAT["P220_fanblur"] = blur; }
        }
        if (blur == null) log.AppendLine("fan blur placeholder material missing");
        try { Mounts(); } catch (System.Exception ex) { log.AppendLine("MOUNTS ERROR " + ex); }

        root = PrefabUtility.LoadPrefabContents(SRC).transform;
        try
        {
            Body();
            Wings();
            MovingPanels();
            Engines();
            Tail();
            Pieces();
            MainGear("L", -1f); MainGear("R", 1f);
            NoseGear();
            Misc();
            Purge();
            Weapons();
            AeroAndDamage();
            FlightControls();
            Rename();
            CockpitP220();
            SkinRegister();
            root.name = "P220Primrose";
            PrefabUtility.SaveAsPrefabAsset(root.gameObject, DST);
            log.AppendLine("saved " + DST);
        }
        catch (System.Exception ex) { log.AppendLine("ERROR " + ex); }
        finally { PrefabUtility.UnloadPrefabContents(root.gameObject); }
        try { Assets(); } catch (System.Exception ex) { log.AppendLine("ASSETS ERROR " + ex); }
        AssetDatabase.SaveAssets();
        return log.ToString();
    }

    // ------------------------------------------------------------------ names: nothing left named after the Medusa; engines numbered from the left
    static void Ren(Transform under, string from, string to)
    {
        var t = Find(under, from); if (t == null) { log.AppendLine("rename: no " + from); return; }
        t.name = to;
    }
    static void Rename()
    {
        Ren(root, "WSO", "copilot");
        Ren(root, "EW1_wheel_F", "wheel_F"); Ren(root, "EW1_gear_F_axle", "gear_F_axle"); Ren(root, "EW1_gear_F_unsprung", "gear_F_unsprung");
        Ren(root, "EW1_gear_F_sprung", "gear_F_sprung"); Ren(root, "EW1_gear_F", "gear_F_strut");
        foreach (var s in new[] { "L", "R" })
        {
            string n = s == "L" ? "1" : "2";
            Ren(Need("gear_" + s), "EW1_wheel_R", "wheel_" + s);
            var py = Need("intake_" + s);
            Ren(py, "intake_" + s + "_lod1", "enginePylon_" + n + "_lod1"); py.name = "enginePylon_" + n;
            var en = Need("engine_" + s);
            Ren(en, "engine_" + s + "_lod1", "engine_" + n + "_lod1");
            Ren(en, "heat_haze_R" + s, "heat_haze_" + n); Ren(en, "backblast_R" + s, "backblast_" + n);
            Ren(en, "thrustTransform_R" + s, "thrustTransform_" + n); Ren(en, "nozzle_R" + s + "_axis", "nozzle_" + n + "_axis");
            Ren(en, "nozzle_R" + s, "nozzle_" + n);
            en.name = "engine_" + n;
        }
        foreach (var t in root.GetComponentsInChildren<Transform>(true))
            if (t.name.Contains("EW1") || t.name.ToLower().Contains("medusa")) log.AppendLine("still Medusa-named: " + t.name);
    }

    // ------------------------------------------------------------------ fuselage, cockpit, crew
    static void Body()
    {
        SetMesh(root, "fuselage"); SetCol(root, "fuselage_colmesh");
        var rl = root.Find("fuselage_lod1"); if (rl != null) rl.GetComponent<MeshFilter>().sharedMesh = M["fuselage_colmesh"];
        PartAt("fuselage_F"); PartAt("cockpit_R"); PartAt("cockpit_F"); PartAt("nose");
        // flight deck glazing, the stock canopy way: outer pane seen from outside, inner pane on the cockpit layer with the
        // stock interior glass shader seen from the seats (0.3.11, the view out was tinted)
        {
            var cf = Need("cockpit_F");
            // 0.4.0: one outer and one inner glass object per side; Pieces() moves each side onto its upper cockpit piece
            int cl = LayerMask.NameToLayer("Cockpit"); if (cl < 0) log.AppendLine("no Cockpit layer");
            foreach (var sd in new[] { "_L", "_R" })
            {
                var gx = Find(cf, "canopy_glass" + sd) ?? New("canopy_glass" + sd, cf); gx.position = P("canopy_glass" + sd); gx.rotation = Quaternion.identity; SetMesh(gx, "canopy_glass" + sd);
                var gi = Find(cf, "canopy_glass_int" + sd) ?? New("canopy_glass_int" + sd, cf); gi.position = P("canopy_glass_int" + sd); gi.rotation = Quaternion.identity; SetMesh(gi, "canopy_glass_int" + sd);
                if (cl >= 0) gi.gameObject.layer = cl;
            }
        }
        // the Medusa crew stations ride cockpit_F, whose pivot puts them on the P220 flight deck; its bubble canopy is
        // hidden (its Canopy components stay for the hangar open/close logic). The Medusa crew doors become the forward
        // passenger doors below.
        foreach (var n in new[] { "canopyFrame", "canopy", "canopy_int", "canopyFrame_int", "canopyFrame_int_simple", "warningLights",
                                  "door_glass_L", "door_glass_R", "door_L_int", "door_R_int" })
        {
            var t = Find(root, n); if (t == null) { log.AppendLine("no " + n); continue; }
            NoMesh(t);
            var mc = t.GetComponent<MeshCollider>(); if (mc != null) mc.enabled = false;
        }
        DoomName("cheek_L"); DoomName("cheek_R");
        ForwardDoors();
        // no ejection seats: the crew bail out through the forward doors, which the stock ejection sequence jettisons in
        // the air (and swings open on the ground), as on the stock aircraft without seats
        foreach (var c in root.GetComponentsInChildren<Component>(true).Where(c => c != null && c.GetType().Name == "Pilot")) Set(c, "ejectionSeat", false);
        foreach (var n in new[] { "RearSeater1", "RearSeater2" })
        {
            // 0.3.30: the two cabin crew sit at the front mission stations, facing their consoles on the wall;
            // drawn again, but their Medusa ejection seats stay hidden
            var t = Need(n); t.position = P(n); t.rotation = Quaternion.Euler(0f, n == "RearSeater1" ? -90f : 90f, 0f);
            foreach (var r in t.GetComponentsInChildren<Renderer>(true)) r.enabled = !(r.transform.name == "EjectionSeat" || r.transform.parent != null && r.transform.parent.name == "EjectionSeat");
            // 0.4.5 (two ejection seats still showed in the cabin): the game turns crew renderers back on, so the seat mesh goes
            foreach (var es in t.GetComponentsInChildren<Transform>(true).Where(x => x.name == "EjectionSeat").ToList()) foreach (var x in es.GetComponentsInChildren<Transform>(true)) NoMesh(x);
        }
        // 0.3.29 (the ejection seats clipped the centre console; no ejection seats on this aircraft): the Medusa
        // seat meshes are hidden and the pilots sit in the airliner seats modelled into the cockpit interior
        int seatsHidden = 0;
        foreach (var es in root.GetComponentsInChildren<Transform>(true).Where(t => t.name == "EjectionSeat" && t.parent != null && (t.parent.name == "pilot" || t.parent.name == "copilot" || t.parent.name == "WSO")).ToList())
        {
            foreach (var r in es.GetComponentsInChildren<Renderer>(true)) r.enabled = false;
            seatsHidden++;
        }
        log.AppendLine("ejection seats hidden: " + seatsHidden);
        // 0.3.30 (the Medusa's rear crew seats and computers showed through the forward doors): its rear crew
        // interior mesh goes; the P220 cabin fit in the fuselage parts replaces it
        { var ri = Find(root, "cockpit_R_int"); if (ri != null) { NoMesh(ri); log.AppendLine("Medusa rear crew interior removed"); } else log.AppendLine("no cockpit_R_int"); }
        foreach (var n in new[] { "targetCamForward", "targetCamRear", "landingCamPoint" }) Need(n).position = P(n);
        var fR = PartAt("fuselage_R");
        foreach (var s in new[] { "L", "R" })
        {
        }
        var tl = PartAt("tail");
        // the flare ejectors sit at the aft ends of the dispenser pods on the lower aft fuselage (moved off the Medusa
        // parts before those go)
        foreach (var s in new[] { "L", "R" }) { var fe = Need("flareEjector_" + s); fe.SetParent(tl, true); fe.position = P("flareEjector_" + s); fe.rotation = Quaternion.LookRotation(new Vector3(Mathf.Sign(fe.position.x) * 0.35f, -1f, -0.3f).normalized, Vector3.forward); }   // flares leave the bottom grid, down and outward
        // the ejection points named the Medusa's aft fuselage pods as their parts; they now belong to the tail
        var fej = C(root, "FlareEjector"); var fso = new SerializedObject(fej); var eps = fso.FindProperty("ejectionPoints");
        for (int i = 0; i < eps.arraySize; i++) eps.GetArrayElementAtIndex(i).FindPropertyRelative("part").objectReferenceValue = C(tl, "AeroPart");
        fso.ApplyModifiedPropertiesWithoutUndo();
        DoomName("fuselage_RL"); DoomName("fuselage_RR");
        var ck = Need("cockpit_F_int");
        var b = ck.GetComponent<Renderer>().bounds;
        log.AppendLine("Medusa cockpit interior bounds " + b.min.ToString("F2") + " .. " + b.max.ToString("F2"));
        log.AppendLine("helmet (pilot) at " + Find(Need("pilot"), "helmetCamPoint").position.ToString("F2"));
    }

    // ------------------------------------------------------------------ P220 flight deck (0.3.12 first pass)
    // Own interior mesh (P220_cockpit.fbx, built by p220_cockpit_model.py) on the Medusa cockpit_F_int, which keeps the stock
    // Cockpit / CockpitWarningLights components. Thrust handles slide through Cockpit.throttles (motion); side sticks are stock ControlSurfaces
    // on the cockpit part; the rudder pedals slide in floor channels, moved by the plugin. Screens show the P220 tac page.
    static void CockpitP220()
    {
        string fbx = ART + "P220_cockpit.fbx";
        var meshes = new Dictionary<string, Mesh>();
        foreach (var o in AssetDatabase.LoadAllAssetsAtPath(fbx)) if (o is Mesh) meshes[o.name] = (Mesh)o;
        var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
        if (model == null || meshes.Count == 0) { log.AppendLine("cockpit: no P220_cockpit.fbx"); return; }
        var cf = Need("cockpit_F"); var ck = Need("cockpit_F_int");
        // textures
        foreach (var n in new[] { "b", "n", "m", "ao" })
        {
            var ti = (TextureImporter)AssetImporter.GetAtPath(ART + "P220_cockpit_" + n + ".png");
            if (ti == null) continue;
            ti.textureType = n == "n" ? TextureImporterType.NormalMap : TextureImporterType.Default;
            ti.sRGBTexture = n == "b"; ti.maxTextureSize = 2048; ti.SaveAndReimport();
        }
        System.Func<string, Texture2D> T = n => AssetDatabase.LoadAssetAtPath<Texture2D>(ART + "P220_cockpit_" + n + ".png");
        var ckMat = AssetDatabase.LoadAssetAtPath<Material>(ART + "P220_cockpit.mat");
        if (ckMat == null) { ckMat = new Material(ck.GetComponent<Renderer>().sharedMaterial); ckMat.name = "P220_cockpit"; AssetDatabase.CreateAsset(ckMat, ART + "P220_cockpit.mat"); }
        foreach (var p in new[] { "_MainTex", "_BaseMap" }) if (ckMat.HasProperty(p)) ckMat.SetTexture(p, T("b"));
        if (ckMat.HasProperty("_BumpMap")) ckMat.SetTexture("_BumpMap", T("n"));
        if (ckMat.HasProperty("_MetallicGlossMap")) ckMat.SetTexture("_MetallicGlossMap", T("m"));
        if (ckMat.HasProperty("_OcclusionMap")) ckMat.SetTexture("_OcclusionMap", T("ao"));
        foreach (var p in new[] { "_Color", "_BaseColor" }) if (ckMat.HasProperty(p)) ckMat.SetColor(p, Color.white);
        EditorUtility.SetDirty(ckMat);
        var mats = new Dictionary<string, Material>
        {
            { "P220_cockpit", ckMat }, { "P220_cabin", PlasticMat() },
            { "tacScreenDisplay", AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/tacScreenDisplay_PLACEHOLDER.mat") },
            { "CockpitWarningLight", AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/CockpitWarningLight_PLACEHOLDER.mat") },
            { "Matte_black", AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/Matte_black_PLACEHOLDER.mat") },
        };
        int layer = ck.gameObject.layer;
        System.Func<string, Material[]> MatsOf = name =>
        {
            var src = model.transform.Cast<Transform>().First(t => t.name == name);
            return src.GetComponent<MeshRenderer>().sharedMaterials.Select(m => mats.First(kv => m.name.StartsWith(kv.Key)).Value).ToArray();
        };
        System.Func<string, Mesh> MeshOf = name => meshes[model.transform.Cast<Transform>().First(t => t.name == name).GetComponent<MeshFilter>().sharedMesh.name];
        System.Func<string, Transform, Vector3, Transform> Part = (name, parent, pivot) =>
        {
            var go = new GameObject("P220_" + name); go.layer = layer;
            go.transform.SetParent(parent, false);
            go.transform.position = root.TransformPoint(pivot); go.transform.rotation = root.rotation;
            go.AddComponent<MeshFilter>().sharedMesh = MeshOf(name);
            go.AddComponent<MeshRenderer>().sharedMaterials = MatsOf(name);
            return go.transform;
        };
        // old Medusa interior pieces go
        foreach (var n in new[] { "joystick_L", "joystick_R", "throttle" })
        { var t = root.GetComponentsInChildren<Transform>(true).FirstOrDefault(x => x.name == n); if (t != null) Object.DestroyImmediate(t.gameObject); }
        foreach (var r in ck.GetComponentsInChildren<Renderer>(true)) if (r.transform != ck) r.enabled = false;
        // 0.3.15: the Medusa's target screen (a pair of glass panes above its panel) is switched back on by the game and showed
        // the P220 page floating over the glareshield: keep the object for any reference to it, but give it no mesh
        { var ts = cf.Find("targetScreen"); if (ts != null) { NoMesh(ts); var tr = ts.GetComponent<Renderer>(); if (tr != null) tr.enabled = false; log.AppendLine("cockpit: Medusa target screen emptied"); } }
        // interior on the stock cockpit object
        ck.GetComponent<MeshFilter>().sharedMesh = MeshOf("cockpit_int");
        ck.GetComponent<MeshRenderer>().sharedMaterials = MatsOf("cockpit_int");
        ck.localScale = Vector3.one;
        ck.position = root.position; ck.rotation = root.rotation;
        var tac = Part("tacScreen", cf, Vector3.zero);
        var lights = Part("warningLights", cf, Vector3.zero);
        // 0.3.17: sliding thrust handles. Stock Cockpit 'motion' sets the handle's localPosition to (0, 0, throttle x range),
        // so the handles sit under an empty track whose origin is the IDLE stop; 0.1655 m of travel ends on the printed TOGA mark
        var thrTrack = new GameObject("P220_throttle_track"); thrTrack.layer = layer;
        thrTrack.transform.SetParent(cf, false);
        thrTrack.transform.position = root.TransformPoint(new Vector3(0f, 0.235f, 16.798f)); thrTrack.transform.rotation = root.rotation;
        var thr = Part("throttle", cf, new Vector3(0f, 0.235f, 16.798f));
        thr.SetParent(thrTrack.transform, true); thr.localPosition = Vector3.zero; thr.localRotation = Quaternion.identity;
        log.AppendLine("cockpit: throttle track scale " + thrTrack.transform.lossyScale.z.ToString("0.###"));
        var simple = Need("cockpit_F_int_simple");
        simple.position = root.position; simple.rotation = root.rotation; simple.localScale = Vector3.one;
        simple.GetComponent<MeshFilter>().sharedMesh = MeshOf("cockpit_int_simple");
        simple.GetComponent<MeshRenderer>().sharedMaterials = MatsOf("cockpit_int_simple");

        var cockpit = C(ck, "Cockpit");
        Set(cockpit, "tacScreenRender", tac.GetComponent<Renderer>());
        { var page = TacScreenP220(); if (page != null) Set(cockpit, "tacScreenUIPrefab", page); }
        // 0.4.2: the page draws into P220_tacScreenRT since 0.3.30, but the stock display material shows the stock target, so the
        // screens stayed blank. The screen gets its own copy of the stock material (black, emission x2) reading our target.
        {
            string tm = ART + "P220_tacScreenDisplay.mat";
            AssetDatabase.DeleteAsset(tm);
            AssetDatabase.CopyAsset(PH + "Material/tacScreenDisplay_PLACEHOLDER.mat", tm);
            var dm = AssetDatabase.LoadAssetAtPath<Material>(tm); dm.name = "P220_tacScreenDisplay";
            var trt = AssetDatabase.LoadAssetAtPath<RenderTexture>(ART + "P220_tacScreenRT.renderTexture");
            if (trt != null) dm.SetTexture("_EmissionMap", trt); else log.AppendLine("tac screen: no P220_tacScreenRT");
            EditorUtility.SetDirty(dm);
            var tr = tac.GetComponent<MeshRenderer>();
            tr.sharedMaterials = tr.sharedMaterials.Select(x => x != null && x.name.StartsWith("tacScreenDisplay") ? dm : x).ToArray();
            log.AppendLine("tac screen material: " + string.Join(",", tr.sharedMaterials.Select(x => x ? x.name : "null")));
        }
        { var so = new SerializedObject(cockpit); so.FindProperty("joysticks").arraySize = 0;
          var th = so.FindProperty("throttles"); th.arraySize = 1; var e = th.GetArrayElementAtIndex(0);
          e.FindPropertyRelative("rotation").boolValue = false; e.FindPropertyRelative("motion").boolValue = true;
          e.FindPropertyRelative("transform").objectReferenceValue = thr; e.FindPropertyRelative("range").floatValue = 0.1655f;
          so.ApplyModifiedPropertiesWithoutUndo(); }
        var cwl = C(ck, "CockpitWarningLights");
        if (cwl != null) { ObjArray(cwl, "lightRenderers", lights.GetComponent<Renderer>()); }
        lights.GetComponent<Renderer>().enabled = false;

        var aero = C(cf, "AeroPart");
        var inside = new List<Object> { ck.GetComponent<Renderer>(), tac.GetComponent<Renderer>(), thr.GetComponent<Renderer>() };
        // side sticks: pitch hinge about root X, roll hinge about root Z (local X turned forward)
        foreach (var s in new[] { "L", "R" })
        {
            var pv = new Vector3(s == "L" ? -0.92f : 0.92f, 0.212f, 16.95f);
            var host = New("P220_stick_" + s, cf); host.gameObject.layer = layer; host.position = root.TransformPoint(pv); host.rotation = root.rotation;
            var hp = New("stick_" + s + "_pitch", host); hp.gameObject.layer = layer; hp.localPosition = Vector3.zero; hp.localRotation = Quaternion.identity;
            CkSurface(host.gameObject, hp.gameObject, aero, 15f, 0f, 0f);
            var host2 = New("stick_" + s + "_rollAxis", hp); host2.gameObject.layer = layer; host2.position = host.position; host2.rotation = root.rotation * Quaternion.AngleAxis(-90f, Vector3.up);
            var hr = New("stick_" + s + "_roll", host2); hr.gameObject.layer = layer; hr.localPosition = Vector3.zero; hr.localRotation = Quaternion.identity;
            CkSurface(host2.gameObject, hr.gameObject, aero, 0f, -15f, 0f);   // 0.3.14: sign flipped (roll was backwards)
            var mesh = Part("stick_" + s, hr, pv);
            inside.Add(mesh.GetComponent<Renderer>());
        }
        // rudder pedals (0.3.14, PB-22 mechanism): each pedal rides a carriage in a floor channel on a raised footrest; the
        // plugin slides the P220_pedal_* parts fore and aft with the rudder input (no stock component moves a part in a line)
        foreach (var n in new[] { "LL", "LR", "RL", "RR" })
        {
            float x = (n[0] == 'L' ? -0.40f : 0.40f) + (n[1] == 'L' ? -0.09f : 0.09f);
            var pv = new Vector3(x, -0.074f, 17.16f);
            inside.Add(Part("pedal_" + n, cf, pv).GetComponent<Renderer>());
        }
        // 0.4.11: gear lever is its own part; the plugin slides it between the DN and UP detents with the gear state
        inside.Add(Part("gearLever", cf, new Vector3(0.71736f, 0.45538f, 17.32177f)).GetComponent<Renderer>());
        var ac = C(root, "Aircraft");
        { var so = new SerializedObject(ac); var cr = so.FindProperty("cockpitRenderers");
          var keep = new List<Object>(); for (int i = 0; i < cr.arraySize; i++) { var o = cr.GetArrayElementAtIndex(i).objectReferenceValue; if (o != null && !inside.Contains(o)) keep.Add(o); }
          so.ApplyModifiedPropertiesWithoutUndo(); keep.AddRange(inside); ObjArray(ac, "cockpitRenderers", keep.ToArray()); }
        log.AppendLine("cockpit: P220 flight deck built, " + inside.Count + " interior renderers");
    }
    // ------------------------------------------------------------------ P220 tac screen page (0.3.14)
    // One stock tac screen render texture (1024x512) feeds every flight deck display; the cockpit model maps each glass to
    // one region (RT_REGIONS in the cockpit layout, pixels from the top-left):
    //   pfd   (0,0,340,262)     outer displays: flight display
    //   tac   (340,0,340,262)   captain's inner display: radar / tac map, target and landing cameras
    //   sys   (680,0,340,262)   first officer's inner display: both engines, fuel and throttle
    //   annun (0,262,512,45)    critical annunciators, 8 cells of 64 (one copy above each pilot)
    //   lamps (512,262,512,112) shared non-critical panel, 8 x 4 cells of 64 x 28 (two rows used)
    // The page is the Medusa page re-laid out with stock HUD apps (Darkreach engine rows). Cells with no stock signal are
    // lit by the plugin (P220Panel), found by the names under P220Annun / P220Lamps.
    static readonly string[] CRIT = { "FIRE 1", "FIRE 2", "MISSILE", "GEAR", "STALL", "FUEL", "HYD", "ELEC" };
    static readonly string[] LAMPS = { "GEAR DN", "FLAP", "SPD BRK", "REV", "BRAKE", "AP", "A/THR", "NAV",
                                       "RADAR", "JAMMER", "LASER", "BAY", "ENG 1", "ENG 2", "APU", "ANTI ICE" };
    // 0.3.29: own copy of the stock HUD extras (as the PB-22 does) so the overspeed warning sits at Mach 0.9
    // (0.9 x 340 m/s at sea level = 306 m/s; the stock gauge takes one fixed airspeed per aircraft)
    static GameObject HudExtras()
    {
        if (!AssetDatabase.IsValidFolder(MOD + "UI")) AssetDatabase.CreateFolder(MOD.TrimEnd('/'), "UI");
        string dst = MOD + "UI/P220_HUDExtras.prefab";
        AssetDatabase.DeleteAsset(dst);
        if (!AssetDatabase.CopyAsset(PH + "GameObject/SFB_HUDExtras_PLACEHOLDER.prefab", dst)) { log.AppendLine("HUD extras: copy failed"); return AssetDatabase.LoadAssetAtPath<GameObject>(PH + "GameObject/SFB_HUDExtras_PLACEHOLDER.prefab"); }
        var go = PrefabUtility.LoadPrefabContents(dst);
        try
        {
            var sg = go.GetComponentsInChildren<Component>(true).FirstOrDefault(c => c != null && c.GetType().Name == "SpeedGauge");
            if (sg == null) log.AppendLine("HUD extras: no SpeedGauge");
            else { var sso = new SerializedObject(sg); sso.FindProperty("overspeedThreshold").floatValue = 306f; sso.ApplyModifiedPropertiesWithoutUndo(); }
            PrefabUtility.SaveAsPrefabAsset(go, dst);
        }
        finally { PrefabUtility.UnloadPrefabContents(go); }
        return AssetDatabase.LoadAssetAtPath<GameObject>(dst);
    }
    static GameObject TacScreenP220()
    {
        string dst = ART + "P220_tacScreen.prefab";
        AssetDatabase.DeleteAsset(dst);
        if (!AssetDatabase.CopyAsset(PH + "GameObject/tacScreen_EW1_PLACEHOLDER.prefab", dst)) { log.AppendLine("tac screen: copy failed"); return null; }
        var sfb = PrefabUtility.LoadPrefabContents(AssetDatabase.GUIDToAssetPath(AssetDatabase.FindAssets("tacScreen_SFB_PLACEHOLDER t:Prefab")[0]));
        var page = PrefabUtility.LoadPrefabContents(dst);
        try
        {
            page.name = "P220_tacScreen";
            System.Func<string, RectTransform> R = n => page.GetComponentsInChildren<RectTransform>(true).First(t => t.name == n);
            var canvas = R("Canvas"); int layer = canvas.gameObject.layer;
            // 0.3.30 (the screen text was too low resolution): the page renders into its own 2048 x 1024 target
            // instead of the stock 1024 x 512 one, and the canvas draws at 2x so the layout keeps its 1024 x 512 units
            {
                var tsc = page.GetComponent(GameType("TacScreen"));
                var stockRt = (RenderTexture)Get(tsc, "renderTexture");
                string rtp = ART + "P220_tacScreenRT.renderTexture";
                var rt = AssetDatabase.LoadAssetAtPath<RenderTexture>(rtp);
                if (rt == null)
                {
                    rt = new RenderTexture(stockRt != null ? stockRt.descriptor : new RenderTextureDescriptor(2048, 1024, RenderTextureFormat.ARGB32, 24));
                    rt.width = 2048; rt.height = 1024; rt.name = "P220_tacScreenRT";
                    AssetDatabase.CreateAsset(rt, rtp);
                }
                rt.width = 2048; rt.height = 1024;
                if (stockRt != null) { rt.antiAliasing = stockRt.antiAliasing; rt.filterMode = FilterMode.Trilinear; rt.useMipMap = stockRt.useMipMap; rt.autoGenerateMips = stockRt.autoGenerateMips; rt.anisoLevel = 4; }
                EditorUtility.SetDirty(rt);
                Set(tsc, "renderTexture", rt);
                var cam = (Camera)Get(tsc, "cam"); if (cam != null) cam.targetTexture = rt;
                var scaler = canvas.GetComponent<UnityEngine.UI.CanvasScaler>(); if (scaler != null) scaler.scaleFactor = 2f;
                log.AppendLine("tac screen render target 2048 x 1024 (stock " + (stockRt != null ? stockRt.width + " x " + stockRt.height : "none") + ")");
            }
            var font = Object.Instantiate(sfb.GetComponentsInChildren<RectTransform>(true).First(t => t.name == "Title Mass").gameObject, page.transform, false);
            font.SetActive(false);
            System.Func<float, float, float, float, Vector2> Rgn = (x, y, w, h) => new Vector2(x + w/2f - 512f, 256f - y - h/2f);
            System.Action<RectTransform, Vector2, float> Place = (t, p, s) =>
            { t.anchorMin = t.anchorMax = t.pivot = new Vector2(0.5f, 0.5f); t.anchoredPosition = p; t.localScale = new Vector3(s, s, 1f); };
            System.Func<string, Transform, Vector2, Vector2, RectTransform> Node = (n, parent, p, size) =>
            {
                var go = new GameObject(n, typeof(RectTransform)); go.layer = layer;
                var t = (RectTransform)go.transform; t.SetParent(parent, false); Place(t, p, 1f); t.sizeDelta = size; return t;
            };
            System.Func<string, Transform, Vector2, Vector2, Color, UnityEngine.UI.Image> Img = (n, parent, p, size, col) =>
            { var im = Node(n, parent, p, size).gameObject.AddComponent<UnityEngine.UI.Image>(); im.color = col; im.raycastTarget = false; return im; };
            System.Func<string, Transform, Vector2, Vector2, string, float, Color, Component> Txt = (n, parent, p, size, text, fs, col) =>
            {
                var go = Object.Instantiate(font, parent, false); go.name = n; go.layer = layer; go.SetActive(true);
                foreach (Transform ch in go.transform.Cast<Transform>().ToArray()) Object.DestroyImmediate(ch.gameObject);
                var t = (RectTransform)go.transform; Place(t, p, 1f); t.sizeDelta = size;
                var tmp = go.GetComponent("TMPro.TextMeshProUGUI"); var ty = tmp.GetType();
                ty.GetProperty("text").SetValue(tmp, text); ty.GetProperty("enableAutoSizing").SetValue(tmp, false);
                ty.GetProperty("fontSize").SetValue(tmp, fs); ty.GetProperty("color").SetValue(tmp, col);
                var al = ty.GetProperty("alignment"); al.SetValue(tmp, System.Enum.Parse(al.PropertyType, "Center"));
                ty.GetProperty("enableWordWrapping").SetValue(tmp, false); ty.GetProperty("raycastTarget").SetValue(tmp, false);
                return tmp;
            };
            System.Action<Transform, Vector2, Vector2, Color> Frame = (parent, p, size, col) =>
            {
                var f = Node("frame", parent, p, size);
                Img("top", f, new Vector2(0, size.y/2f - 1f), new Vector2(size.x, 2f), col);
                Img("bottom", f, new Vector2(0, -size.y/2f + 1f), new Vector2(size.x, 2f), col);
                Img("left", f, new Vector2(-size.x/2f + 1f, 0), new Vector2(2f, size.y), col);
                Img("right", f, new Vector2(size.x/2f - 1f, 0), new Vector2(2f, size.y), col);
            };
            var green = new Color(0f, 1f, 0f, 1f); var frameCol = new Color(0f, 1f, 0f, 0.35f);
            var legend = new Color(0.42f, 0.42f, 0.40f, 1f); var off = new Color(0.055f, 0.06f, 0.055f, 1f);
            var red = new Color(1f, 0.1f, 0.05f, 1f); var amber = new Color(1f, 0.62f, 0f, 1f);

            // ---------------- pfd: the stock flight instrument filling the outer displays, clock top left
            var pfd = Rgn(0, 0, 340, 262);
            var bfi = R("BasicFlightInstrument"); Place(bfi, pfd, 1.25f);
            var bfiImg = bfi.GetComponent<UnityEngine.UI.Image>(); if (bfiImg != null) bfiImg.enabled = true;
            Place(R("TimeObject"), pfd + new Vector2(-118f, 116f), 0.8f);

            // ---------------- tac: radar scope filling the inner glass, camera feeds over it with black bars
            var tacC = Rgn(340, 0, 340, 262);
            Place(R("Radar"), tacC, 256f/512f);
            foreach (var cn in new[] { "TargetCam", "LandingCam" })
            {
                var cam = R(cn); Place(cam, tacC, 1f); float fh = 340f*240f/360f; cam.sizeDelta = new Vector2(340f, fh);
                var raw = cam.GetComponent<UnityEngine.UI.RawImage>(); if (raw != null) raw.uvRect = new Rect(0f, 0f, 1f, 1f);
                float bh = (262f - fh)/2f;
                Img("P220_barTop", cam, new Vector2(0f, (fh + bh)/2f), new Vector2(340f, bh), Color.black);
                Img("P220_barBottom", cam, new Vector2(0f, -(fh + bh)/2f), new Vector2(340f, bh), Color.black);
            }
            foreach (var n in new[] { "Buttons", "divider", "divider (2)", "WeaponPanel" })
            { var t = page.GetComponentsInChildren<RectTransform>(true).FirstOrDefault(x => x.name == n); if (t != null) t.gameObject.SetActive(false); }
            canvas.Find("border").gameObject.SetActive(false);

            // ---------------- sys: both engines (Darkreach engine rows) and the fuel and throttle bars
            var sys = Rgn(680, 0, 340, 262);
            Frame(canvas, sys, new Vector2(336f, 258f), frameCol);
            var engRows = Node("EngineRows", canvas, sys + new Vector2(-44f, 0f), new Vector2(330f, 220f)); engRows.localScale = new Vector3(0.75f, 0.75f, 1f);
            var sfbEng = sfb.GetComponentsInChildren<RectTransform>(true);
            foreach (var side in new[] { "1", "2" })
            {
                var row = (RectTransform)Object.Instantiate(sfbEng.First(t => t.name == (side == "1" ? "engL" : "engR")).gameObject, engRows, false).transform;
                row.name = "eng" + side; foreach (var c in row.GetComponentsInChildren<Transform>(true)) c.gameObject.layer = layer;
                Object.DestroyImmediate(row.GetComponent<UnityEngine.UI.VerticalLayoutGroup>());
                Place(row, new Vector2(0f, side == "1" ? 58f : -58f), 1f); row.sizeDelta = new Vector2(326f, 104f);
                var title = (RectTransform)row.Find("Title"); Place(title, new Vector2(-115f, 18f), 0.6f);
                var ttm = title.GetComponent("TMPro.TextMeshProUGUI"); ttm.GetType().GetProperty("text").SetValue(ttm, "ENG " + side);
                ((RectTransform)title.Find("status")).anchoredPosition = new Vector2(85f, -50f);
                float[] xs = { -28f, 46f, 120f }; string[] dials = { "ThrustGauge1", "RPMGauge1", "ThrottleGauge1" };
                for (int k = 0; k < 3; k++) Place((RectTransform)row.Find(dials[k]), new Vector2(xs[k], 6f), 0.9f);
                var et = row.GetComponent(GameType("EngineTelemetry"));
                Set(et, "engineName", "engine_" + side);          // the Turbojet parts (renamed from engine_L / engine_R)
                Set(et, "thrustGauge.maxValue", 130000f); Set(et, "rpmGauge.maxValue", 3000f); Set(et, "throttleGauge.maxValue", 100f);
            }
            var sg = R("StatusGauges"); Place(sg, sys + new Vector2(125f, -4f), 1f); sg.sizeDelta = new Vector2(84f, 214f);
            Place((RectTransform)sg.Find("Fuel"), new Vector2(-20f, -10f), 0.8f);
            Place((RectTransform)sg.Find("Throttle"), new Vector2(20f, -10f), 0.8f);
            foreach (var tn in new[] { "Fuel/Title Fuel", "Throttle/Title Throttle" })
            {
                var tt = (RectTransform)sg.Find(tn); if (tt == null) continue; tt.localScale = new Vector3(0.4f, 0.4f, 1f);
                var tmp = tt.GetComponent("TMPro.TextMeshProUGUI"); if (tn.EndsWith("Throttle")) tmp.GetType().GetProperty("text").SetValue(tmp, "THR");
            }
            foreach (var n in new[] { "IRGauge", "Mass", "TWR" }) { var t = sg.Find(n); if (t != null) t.gameObject.SetActive(false); }

            // ---------------- annunciators: critical strip (lit cells) and the shared panel (lit or bar cells)
            var lit = new Dictionary<string, UnityEngine.UI.Image>(); var bar = new Dictionary<string, UnityEngine.UI.Image>(); var txt = new Dictionary<string, Component>();
            var annun = Node("P220Annun", canvas, Rgn(0, 262, 512, 45), new Vector2(512f, 45f));
            Img("bg", annun, Vector2.zero, new Vector2(512f, 45f), new Color(0.02f, 0.02f, 0.02f, 1f));
            for (int k = 0; k < CRIT.Length; k++)
            {
                string n = CRIT[k]; bool redCell = k < 5;
                var cell = Node("crit_" + n, annun, new Vector2(-256f + 32f + k*64f, 0f), new Vector2(60f, 41f));
                Img("off", cell, Vector2.zero, new Vector2(60f, 41f), off);
                var f = Img("lit", cell, Vector2.zero, new Vector2(60f, 41f), redCell ? red : amber); f.enabled = false; lit["crit_" + n] = f;
                var lg = Txt("legend", cell, Vector2.zero, new Vector2(58f, 36f), n, 13f, legend);
                // 0.3.29: the glareshield strip shows this 512 x 45 region about 9% wider than it is: narrow the lettering to match
                ((Component)lg).transform.localScale = new Vector3(0.92f, 1f, 1f);
            }
            annun.SetAsLastSibling();
            var lamps = Node("P220Lamps", canvas, Rgn(512, 262, 512, 112), new Vector2(512f, 112f));
            Img("bg", lamps, Vector2.zero, new Vector2(512f, 112f), new Color(0.02f, 0.02f, 0.02f, 1f));
            var barCells = new HashSet<string> { "RADAR", "AP", "NAV", "ENG 1", "ENG 2" };
            for (int k = 0; k < LAMPS.Length; k++)
            {
                string n = LAMPS[k];
                var cell = Node("lamp_" + n.Replace("/", ""), lamps,   // no "/" in object names: Blueprinter resolves assets by hierarchy path
                                new Vector2(-256f + 32f + (k % 8)*64f, 56f - 14f - (k / 8)*28f), new Vector2(62f, 26f));
                Img("off", cell, Vector2.zero, new Vector2(62f, 26f), off);
                if (barCells.Contains(n)) bar[n] = Img("bar", cell, new Vector2(0f, -11f), new Vector2(54f, 2f), legend);
                else { var col = n == "GEAR DN" ? green : (n == "BRAKE" || n == "SPD BRK" || n == "REV" || n == "FLAP" ? amber : green);
                       var f = Img("lit", cell, Vector2.zero, new Vector2(62f, 26f), col); f.enabled = false; lit["lamp_" + n] = f; }
                txt[n] = Txt("legend", cell, Vector2.zero, new Vector2(60f, 22f), n, 11f, legend);
                // 0.3.29: each 62 x 26 px cell is shown on a lamp face about 1.33:1, so the lettering came out tall and narrow.
                // Squash it here by the same ratio (0.56), split between width and height so it still fills the cell.
                { var lt = (RectTransform)((Component)txt[n]).transform; lt.localScale = new Vector3(1.15f, 0.64f, 1f); lt.sizeDelta = new Vector2(52f, 34f); }
                if (barCells.Contains(n) && n != "ENG 1" && n != "ENG 2")
                {   // SystemStatusDisplay writes its own text here ("MODE : NAV" and so on)
                    var tm = txt[n]; var ty = tm.GetType();
                    ty.GetProperty("enableAutoSizing").SetValue(tm, true); ty.GetProperty("fontSizeMin").SetValue(tm, 5f); ty.GetProperty("fontSizeMax").SetValue(tm, 11f);
                }
            }
            lamps.SetAsLastSibling();

            var apps = new List<Object>();
            var gi = annun.gameObject.AddComponent(GameType("GearIndicator"));
            Set(gi, "speedLimit", 100000f); Set(gi, "gearIcon", lit["lamp_GEAR DN"]); Set(gi, "brakeIcon", lit["lamp_BRAKE"]); Set(gi, "lowerGearWarning", false);
            Set(gi, "lowerGearText", Txt("lowerGearText", annun, new Vector2(0f, 400f), new Vector2(10f, 10f), "", 8f, legend));
            apps.Add(gi);
            var mw = annun.gameObject.AddComponent(GameType("MissileWarningLight"));
            ObjArray(mw, "images", lit["crit_MISSILE"]); apps.Add(mw);
            var ss = R("SystemStatus"); var ssd = ss.GetComponent(GameType("SystemStatusDisplay"));
            Set(ssd, "systemRadarImg", bar["RADAR"]); Set(ssd, "systemRadarTxt", txt["RADAR"]);
            Set(ssd, "systemFlightControlImg", bar["AP"]); Set(ssd, "systemFlightControlTxt", txt["AP"]);
            Set(ssd, "systemModeImg", bar["NAV"]); Set(ssd, "systemModeTxt", txt["NAV"]);
            ss.gameObject.GetComponent<UnityEngine.UI.GridLayoutGroup>().enabled = false;
            Place(ss, new Vector2(0f, 3000f), 1f);
            var modeT = ss.Find("SystemMode"); if (modeT != null && modeT.Find("Mode") != null) modeT.Find("Mode").gameObject.SetActive(false);
            foreach (var side in new[] { "1", "2" })
            {
                var so = new SerializedObject(engRows.Find("eng" + side).GetComponent(GameType("EngineTelemetry")));
                var ci = so.FindProperty("colorableImages"); ci.arraySize++; ci.GetArrayElementAtIndex(ci.arraySize - 1).objectReferenceValue = bar["ENG " + side];
                var ct = so.FindProperty("colorableTexts"); ct.arraySize++; ct.GetArrayElementAtIndex(ct.arraySize - 1).objectReferenceValue = txt["ENG " + side];
                so.ApplyModifiedPropertiesWithoutUndo();
            }
            var mgr = page.GetComponent(GameType("MFDAppManager"));
            ObjArray(mgr, "apps", new Object[] { ssd, sg.GetComponent(GameType("StatusGauges")), bfi.GetComponent(GameType("BasicFlightInstruments")) }.Concat(apps).ToArray());
            foreach (var n in new[] { "engPanel1", "engPanel2", "nozzleGauge" }) Object.DestroyImmediate(R(n).gameObject);
            Object.DestroyImmediate(font);
            log.AppendLine("tac screen: P220 page, " + new SerializedObject(mgr).FindProperty("apps").arraySize + " apps, " + lit.Count + " lit cells, " + bar.Count + " bar cells");
            PrefabUtility.SaveAsPrefabAsset(page, dst);
        }
        finally { PrefabUtility.UnloadPrefabContents(page); PrefabUtility.UnloadPrefabContents(sfb); }
        return AssetDatabase.LoadAssetAtPath<GameObject>(dst);
    }
    static void CkSurface(GameObject host, GameObject hinge, Component aero, float pitch, float roll, float yaw)
    {
        var cs = host.AddComponent(GameType("ControlSurface"));
        Set(cs, "pitchRange", pitch); Set(cs, "rollRange", roll); Set(cs, "yawRange", yaw); Set(cs, "brakeRange", 0f);
        Set(cs, "attachedSurface", aero); Set(cs, "visibleMesh", hinge); Set(cs, "flap", false);
        Set(cs, "servoSpeed", 120f); Set(cs, "maxVolumeSpeed", 340f); Set(cs, "splitPitchMin", 0.5f); Set(cs, "splitPitchMax", 2f);
    }

    // ------------------------------------------------------------------ forward doors (the Medusa crew door Canopies)
    static void ForwardDoors()
    {
        foreach (var s in new[] { "L", "R" })
        {
            var door = Need("door_" + s); var hinge = door.parent; var mount = hinge.parent;
            var hp = P("fdoor_" + s + "_hinge"); var at = P("fdoor_" + s + "_attach");
            // airline door: an arm pivots inside the cabin ahead of the doorway (vertical axis) and swings the door out
            // and forward; the door turns back the same angle on the arm end so it stays parallel to the fuselage.
            // CanopyHinge turns its transform about local X: point local X straight up for vertical hinge lines
            var up = Quaternion.FromToRotation(Vector3.right, Vector3.up);
            mount.position = hp; mount.rotation = up;
            hinge.localPosition = Vector3.zero; hinge.localRotation = Quaternion.identity; hinge.name = "doorArm_" + s;
            var armMesh = New("doorArmMesh_" + s, hinge); armMesh.position = hp; armMesh.rotation = Quaternion.identity; SetMesh(armMesh, "fdoor_arm_" + s);
            var pivot = New("doorPivot_" + s, hinge); pivot.position = at; pivot.rotation = up;
            door.SetParent(pivot, true);
            door.position = P("fdoor_" + s); door.rotation = Quaternion.identity; door.localScale = Vector3.one;
            SetMesh(door, "fdoor_" + s);
            var mc = door.GetComponent<MeshCollider>();
            if (mc != null) { mc.convex = true; mc.sharedMesh = M["fdoor_" + s + "_colmesh"]; }
            foreach (Transform ch in door) NoMesh(ch);
            var rend = door.GetComponent<Renderer>();
            float x0 = Mathf.Abs(rend.bounds.center.x), z0 = rend.bounds.center.z;
            System.Func<float, Vector3> tryOpen = a2 => { hinge.localEulerAngles = Vector3.right * a2; pivot.localEulerAngles = Vector3.right * -a2; var c = rend.bounds.center; hinge.localRotation = Quaternion.identity; pivot.localRotation = Quaternion.identity; return c; };
            // the opening sense is the one that carries the door forward (towards +z, the nose) and outboard
            var ca = tryOpen(60f); var cb = tryOpen(-60f);
            float open = ca.z > cb.z ? 60f : -60f; var co = open > 0 ? ca : cb;
            var cso = new SerializedObject(C(door, "Canopy"));
            var hs = cso.FindProperty("canopyHinges"); hs.arraySize = 2;
            hs.GetArrayElementAtIndex(0).FindPropertyRelative("transform").objectReferenceValue = hinge;
            hs.GetArrayElementAtIndex(0).FindPropertyRelative("hingeAngle").floatValue = open;
            hs.GetArrayElementAtIndex(1).FindPropertyRelative("transform").objectReferenceValue = pivot;
            hs.GetArrayElementAtIndex(1).FindPropertyRelative("hingeAngle").floatValue = -open;
            cso.FindProperty("forcePosition").vector3Value = new Vector3(s == "L" ? -1f : 1f, 0f, 0f);
            // the Medusa blows its crew doors off with 20 kN; an airliner door just drops away (far less force)
            cso.FindProperty("ejectionForce").vector3Value = new Vector3(0f, 3000f, 0f);
            cso.ApplyModifiedPropertiesWithoutUndo();
            log.AppendLine("forward door " + s + " arm " + open + ": centre moves " + (co.z - z0).ToString("F2") + " fwd, " + (Mathf.Abs(co.x) - x0).ToString("F2") + " out");
        }
    }

    // ------------------------------------------------------------------ rear weapons bay: Medusa bay doors and hardpoint, plus a second hardpoint
    static void WeaponBay()
    {
        var fR = Need("fuselage_R");
        foreach (var s in new[] { "L", "R" })
        {
            var mount = Need("weapon_door_mount_" + s); var hinge = Need("weapon_door_hinge_" + s);
            mount.SetParent(fR, true);
            var a = P("baydoor_" + s + "_hingeA"); var b = P("baydoor_" + s + "_hingeB");
            mount.position = (a + b) * 0.5f; mount.rotation = Quaternion.identity;
            hinge.localPosition = Vector3.zero; hinge.localRotation = Quaternion.identity;
            foreach (Transform ch in hinge) NoMesh(ch);
            var dm = Find(hinge, "baydoor_mesh_" + s); if (dm == null) dm = New("baydoor_mesh_" + s, hinge);
            dm.position = P("baydoor_" + s); dm.rotation = Quaternion.identity; dm.localScale = Vector3.one;
            SetMesh(dm, "baydoor_" + s);
            // BayDoor turns about local Z (fore-aft); open to whichever side swings the door's inner edge down
            float y0 = dm.GetComponent<Renderer>().bounds.center.y;
            hinge.localEulerAngles = new Vector3(0f, 0f, 110f); float ya = dm.GetComponent<Renderer>().bounds.center.y;
            hinge.localEulerAngles = new Vector3(0f, 0f, -110f); float yb = dm.GetComponent<Renderer>().bounds.center.y;
            hinge.localRotation = Quaternion.identity;
            Set(C(hinge, "BayDoor"), "hingeAngle", ya < yb ? 110f : -110f);
            log.AppendLine("bay door " + s + " opens " + (ya < yb ? 110f : -110f) + " (closed y " + y0.ToString("F2") + ")");
        }
        var hl = Need("weaponBayHardpoint"); hl.SetParent(fR, true); hl.position = P("bayHardpoint_L"); hl.rotation = Quaternion.identity;
        var hr = Find(root, "weaponBayHardpoint_R"); if (hr == null) hr = New("weaponBayHardpoint_R", fR);
        hr.position = P("bayHardpoint_R"); hr.rotation = Quaternion.identity;
    }

    // ------------------------------------------------------------------ control surfaces: AeroPart on the hinge line, hinge X along the hinge line, mesh world-aligned
    static void Surface(string part, string hingeName, string visName, string mesh, Vector3 a, Vector3 b, Transform liftNormal)
    {
        var t = Need(part);
        var mid = (a + b) * 0.5f;
        // 0.4.11: the part and its visible mesh sit at the mesh origin (= hinge midpoint on whole surfaces, but the
        // tip pieces are centred on their own bounds, so placing them on the hinge midpoint shifted them ~25 cm)
        var org = P(mesh);
        t.position = org; t.rotation = Quaternion.identity;
        NoMesh(t); SetCol(t, mesh + "_colmesh");
        var h = Find(root, hingeName);
        if (h == null) h = New(hingeName, t);
        if (h.parent != t) h.SetParent(t, true);
        var dir = (b - a).normalized; if (Vector3.Dot(dir, Vector3.right) < 0f && Mathf.Abs(dir.x) > 0.5f) dir = -dir;
        h.position = mid; h.rotation = Quaternion.FromToRotation(Vector3.right, dir);
        var v = Find(h, visName);
        if (v == null) v = New(visName, h);
        v.position = org; v.rotation = Quaternion.identity;
        SetMesh(v, mesh);
        var lod = Find(v, part + "_lod1") ?? Find(t, part + "_lod1");
        if (lod != null) { lod.SetParent(v, false); lod.localPosition = Vector3.zero; lod.localRotation = Quaternion.identity; lod.GetComponent<MeshFilter>().sharedMesh = M[mesh + "_colmesh"]; }
        if (liftNormal != null) Set(C(t, "AeroPart"), "liftNormal", liftNormal);
    }

    // ------------------------------------------------------------------ wings, flaps, ailerons, pylons, nav lights
    static void Wings()
    {
        foreach (var s in new[] { "L", "R" })
        {
            PartAt("wing1a_" + s); PartAt("wing1b_" + s); PartAt("wing2_" + s); PartAt("wing3_" + s); PartAt("wingtip_" + s);
            DoomName("slat1_" + s); DoomName("slat2_" + s); DoomName("pylon_" + s + "2"); DoomName("gear_" + s + "_armTarget");
            var py = Need("pylon_" + s + "1"); py.position = P("pylon_" + s + "1"); py.rotation = Quaternion.identity;
            // the Medusa lens mesh sits 0.45 m off its own pivot: place it by its bounds so the lens sits on the tip
            var nl = Need("navlight_" + s); nl.position = P("navlight_" + s);
            var nlr = nl.GetComponent<Renderer>();
            if (nlr != null) nl.position += P("navlight_" + s) - nlr.bounds.center;
            var nle = Need("navlight_" + s + "_effects"); nle.position = (nlr != null ? nlr.bounds.center : P("navlight_" + s)) + new Vector3(0f, 0f, 0.27f);   // glow at the lens face
            Need("wingtipvortex_" + s).position = P("navlight_" + s);
            var wv = Need("wingVapor_" + s); wv.position = P("wing2_" + s);
            // aileron (Medusa hierarchy: aileron_X > aileron_X_hinge > aileron_X_visible)
            Surface("aileron_" + s, "aileron_" + s + "_hinge", "aileron_" + s + "_visible", "aileron_" + s,
                    P("aileron_" + s + "_hingeA"), P("aileron_" + s + "_hingeB"), null);
            Set(C(Need("aileron_" + s), "AeroPart"), "liftNormal", Need("aileron_" + s + "_hinge"));
            // flap: the Medusa flap is a fixed panel; ours hinges and deploys with the gear (ControlSurface flap mode)
            var flap = Need("flap_" + s);
            var flapLod = flap.Find("flap_" + s + "_lod1");
            NoMesh(flap); var fr = flap.GetComponent<MeshRenderer>(); if (fr != null) fr.enabled = false;
            Surface("flap_" + s, "flap_" + s + "_hinge", "flap_" + s + "_visible", "flap_" + s,
                    P("flap_" + s + "_hingeA"), P("flap_" + s + "_hingeB"), null);
            if (flapLod != null) { flapLod.SetParent(Need("flap_" + s + "_visible"), false); flapLod.localPosition = Vector3.zero; flapLod.localRotation = Quaternion.identity; flapLod.GetComponent<MeshFilter>().sharedMesh = M["flap_" + s + "_colmesh"]; }
            var cs = C(flap, "ControlSurface");
            if (cs == null)
            {
                UnityEditorInternal.ComponentUtility.CopyComponent(C(Need("aileron_" + s), "ControlSurface"));
                UnityEditorInternal.ComponentUtility.PasteComponentAsNew(flap.gameObject);
                cs = C(flap, "ControlSurface");
            }
            Set(cs, "attachedSurface", C(flap, "AeroPart"));
            Set(cs, "visibleMesh", Need("flap_" + s + "_hinge").gameObject);
            Set(cs, "flap", true); Set(cs, "pitchRange", 15f); Set(cs, "rollRange", 0f); Set(cs, "yawRange", 0f); Set(cs, "servoSpeed", 12f);
            Set(C(flap, "AeroPart"), "liftNormal", Need("flap_" + s + "_hinge"));
            var dm = C(flap, "AeroPart");
            ObjArray(dm, "damageMaterial.renderers", Need("flap_" + s + "_visible").GetComponent<MeshRenderer>());
        }
    }


    // ------------------------------------------------------------------ inboard flaps, slats, spoilers
    // a panel on a hinge line from the layout: mount (local X along the hinge) > hinge > visible mesh (world-aligned).
    // The hinge direction is chosen so that turning the hinge by testDeg moves the panel the wanted way (up +1, down -1).
    static Transform Hinged(string mesh, Transform parent, float testDeg, float want, out Transform rest)
    {
        var a = P(mesh + "_hingeA"); var b = P(mesh + "_hingeB"); var dir = (b - a).normalized;
        var mount = New(mesh + "_mount", parent); mount.position = (a + b) * 0.5f;
        var hinge = New(mesh + "_hinge", mount); var vis = New(mesh + "_visible", hinge);
        rest = New(mesh + "_rest", mount);
        for (int k = 0; k < 2; k++)
        {
            mount.rotation = Quaternion.FromToRotation(Vector3.right, k == 0 ? dir : -dir);
            hinge.localPosition = Vector3.zero; hinge.localRotation = Quaternion.identity;
            vis.position = P(mesh); vis.rotation = Quaternion.identity;
            SetMesh(vis, mesh);
            var c = M[mesh].bounds.center; float y0 = vis.TransformPoint(c).y;
            hinge.localEulerAngles = new Vector3(testDeg, 0f, 0f); float y1 = vis.TransformPoint(c).y;
            hinge.localRotation = Quaternion.identity;
            if ((y1 - y0) * want > 0f) break;
        }
        rest.localPosition = Vector3.zero; rest.localRotation = Quaternion.identity;
        return hinge;
    }
    static Component NewSurface(Transform on, Component like)
    {
        UnityEditorInternal.ComponentUtility.CopyComponent(like);
        UnityEditorInternal.ComponentUtility.PasteComponentAsNew(on.gameObject);
        var all = on.GetComponents<Component>().Where(c => c != null && c.GetType().Name == "ControlSurface").ToArray();
        var cs = all[all.Length - 1];
        Set(cs, "pitchRange", 0f); Set(cs, "rollRange", 0f); Set(cs, "yawRange", 0f); Set(cs, "maxSplit", 0f);
        Set(cs, "splitUpper", null); Set(cs, "splitLower", null);
        return cs;
    }
    static void MovingPanels()
    {
        foreach (var s in new[] { "L", "R" })
        {
            var flap = Need("flap_" + s); var flapCS = C(flap, "ControlSurface"); var aileronCS = C(Need("aileron_" + s), "ControlSurface");
            Transform rest;
            // inboard flap: its own hinge on the same AeroPart, deploying with the gear like the outboard flap
            var inHinge = Hinged("flapin_" + s, flap, -20f, -1f, out rest); Object.DestroyImmediate(rest.gameObject);
            var col = New("flapin_" + s + "_col", flap); col.position = P("flapin_" + s); col.rotation = Quaternion.identity; SetCol(col, "flapin_" + s + "_colmesh");
            var inCS = NewSurface(flap, flapCS);
            Set(inCS, "attachedSurface", C(flap, "AeroPart")); Set(inCS, "visibleMesh", inHinge.gameObject);
            Set(inCS, "flap", true); Set(inCS, "pitchRange", 15f); Set(inCS, "servoSpeed", 12f);
            // spoilers: the flaps' split surfaces, raised at idle throttle (speed brakes and ground spoilers)
            Transform rIn, rOut;
            var spIn = Hinged("spoilerin_" + s, Need("wing1b_" + s), 30f, 1f, out rIn);
            var spOut = Hinged("spoilerout_" + s, Need("wing2_" + s), 30f, 1f, out rOut);
            foreach (var pr in new[] { new { cs = inCS, up = spIn, lo = rIn }, new { cs = flapCS, up = spOut, lo = rOut } })
            {
                Set(pr.cs, "splitUpper", pr.up); Set(pr.cs, "splitLower", pr.lo);
                Set(pr.cs, "maxSplit", 40f); Set(pr.cs, "splitDrag", 0.012f); Set(pr.cs, "yawSplitFactor", 0f);
            }
            // slats droop with the flaps
            foreach (var sl in new[] { new { m = "slat1_" + s, w = "wing2_" + s }, new { m = "slat2_" + s, w = "wing3_" + s } })
            {
                var wing = Need(sl.w);
                var h = Hinged(sl.m, wing, -20f, -1f, out rest); Object.DestroyImmediate(rest.gameObject);
                var cs = NewSurface(wing, aileronCS);
                Set(cs, "attachedSurface", C(wing, "AeroPart")); Set(cs, "visibleMesh", h.gameObject);
                Set(cs, "flap", true); Set(cs, "pitchRange", 20f); Set(cs, "servoSpeed", 10f);
            }
        }
        log.AppendLine("inboard flaps, spoilers (split surfaces) and slats added");
    }

    // ------------------------------------------------------------------ engines: Medusa side intakes become underwing pylons, engines hang under them
    static void Engines()
    {
        DoomComp(C(root, "DuctedThrustSystem"));
        // the Medusa radar jammer (ECM) and flare dispenser stay with their Medusa values for now; smaller capacitor
        Set(C(root, "PowerSupply"), "maxCharge", 600f);
        // the aircraft sensor that cues the tail laser scans every second instead of every two (missiles close ~1 km/s)
        var eots = C(root, "TargetDetector"); Set(eots, "checkInterval", 1f); Set(eots, "alertCheckInterval", 0.5f);
        DoomName("intake_F"); DoomName("nozzle_FL"); DoomName("nozzle_FR");
        foreach (var s in new[] { "L", "R" })
        {
            var pylon = Need("intake_" + s); pylon.SetParent(Need("wing1b_" + s), true);
            PartAt("intake_" + s);
            foreach (Transform c in pylon.Cast<Transform>().ToArray())
                if (c.name.StartsWith("intakedoor") || c.name.StartsWith("slimelight")) Doom(c);
            var en = Need("engine_" + s); en.SetParent(pylon, true);
            PartAt("engine_" + s);
            var ax = Need("nozzle_R" + s + "_axis"); ax.position = P("nozzle_" + s); ax.rotation = Quaternion.identity;
            var nz = Need("nozzle_R" + s); nz.localPosition = Vector3.zero; nz.localRotation = Quaternion.identity; SetMesh(nz, "nozzle_" + s);
            var tt = Need("thrustTransform_R" + s); tt.position = P("thrust_" + s); tt.rotation = Quaternion.identity;
            foreach (Transform fx in tt) { fx.localPosition = Vector3.zero; fx.localRotation = Quaternion.Euler(0f, 180f, 0f); }
            var tj = C(en, "Turbojet");
            ObjArray(tj, "nozzles", C(nz, "JetNozzle"));
            Set(C(nz, "JetNozzle"), "part", C(en, "AeroPart"));
            Reversers(s, en);
            // 0.3.29: fan blades, blur disc and spinner on one pivot on the engine axis; the plugin spins them from the
            // engine RPM and swaps blades for the blur disc at speed (the stock DuctedFan's slow/fast mesh convention)
            foreach (var fp in new[] { "fan_", "fanblur_", "spinner_" })
            {
                var ft = New("P220_" + fp.TrimEnd('_'), en); ft.position = P("fanAxis_" + s); ft.rotation = Quaternion.identity;
                var fm = New("P220_" + fp.TrimEnd('_') + "_mesh", ft); fm.localPosition = Vector3.zero; fm.localRotation = Quaternion.identity;
                SetMesh(fm, fp + s);
                if (fp == "fanblur_") fm.gameObject.SetActive(false);
            }
            // fire warnings name the engines by number, as the cockpit does
            Set(tj, "failureMessage", s == "L" ? "ENGINE 1 FIRE" : "ENGINE 2 FIRE");
            var clip = AssetDatabase.LoadMainAssetAtPath(Placeholder(s == "L" ? "engine1Fire" : "engine2Fire", "AudioClip"));
            if (clip != null) Set(tj, "failureMessageAudio", clip); else log.AppendLine("no engine fire clip");
        }
    }
    // thrust reversers: four pivoting doors at the back of each cowl. A stock Airbrake on the engine swings them open at idle
    // throttle (forward edges out, aft edges into the bypass duct) and adds the braking drag; the plugin holds them shut
    // unless the landing gear is down and locked
    static System.Type GameType(string n)
    {
        foreach (var a in System.AppDomain.CurrentDomain.GetAssemblies()) { var t = a.GetType(n); if (t != null) return t; }
        return null;
    }
    // a mesh built along one axis from its pivot, put under a holder that aims along +Z (for AimConstraints)
    static Transform AimedMesh(string name, Transform parent, Vector3 pos, Vector3 target, Vector3 up, string mesh)
    {
        var t = New(name, parent); t.position = pos; t.rotation = Quaternion.LookRotation(target - pos, up);
        var mt = New(name + "_mesh", t); var b = M[mesh].bounds.center;
        mt.localRotation = Quaternion.FromToRotation(b.normalized, Vector3.forward); SetMesh(mt, mesh);
        return t;
    }
    static Component Aim(Transform t, Transform target, Transform upObj, Vector3 upWorld)
    {
        var ac = t.gameObject.AddComponent<UnityEngine.Animations.AimConstraint>();
        ac.aimVector = Vector3.forward; ac.upVector = Vector3.up;
        ac.worldUpType = UnityEngine.Animations.AimConstraint.WorldUpType.ObjectRotationUp;
        ac.worldUpObject = upObj; ac.worldUpVector = upObj.InverseTransformDirection(upWorld);
        ac.AddSource(new UnityEngine.Animations.ConstraintSource { sourceTransform = target, weight = 1f });
        ac.rotationAtRest = t.localEulerAngles; ac.rotationOffset = Vector3.zero;
        ac.locked = true; ac.constraintActive = true; ac.enabled = false;   // the Airbrake enables it while the doors move
        return ac;
    }
    static void Reversers(string s, Transform en)
    {
        string num = s == "L" ? "1" : "2";
        var axis = P("engineAxis_" + s); var hinges = new List<Transform>(); var aims = new List<Component>[] { new List<Component>(), new List<Component>() };
        for (int k = 1; k <= 4; k++)
        {
            string dn = "revdoor_" + s + k;
            var hp = P(dn + "_hinge"); var radial = hp - axis; radial.z = 0f; radial.Normalize();
            var h = New("reverserHinge_" + num + "_" + k, en);
            h.position = hp; h.rotation = Quaternion.LookRotation(Vector3.forward, radial);   // local X runs round the cowl
            var d = New("reverserDoor_" + num + "_" + k, h); d.position = hp; d.rotation = Quaternion.identity; SetMesh(d, dn);
            hinges.Add(h);
            // hydraulic actuator: cylinder on the fixed cowl, rod on the door, each aimed at the other's pivot
            var anc = P("revcyl_" + s + k); var lug = P("revrod_" + s + k);
            var cyl = AimedMesh("reverserActuator_" + num + "_" + k, en, anc, lug, radial, "revcyl_" + s + k);
            var rodT = AimedMesh("reverserRod_" + num + "_" + k, d, lug, anc, radial, "revrod_" + s + k);
            int set = (k == 2 || k == 3) ? 1 : 0;
            aims[set].Add(Aim(cyl, rodT, en, radial)); aims[set].Add(Aim(rodT, cyl, en, radial));
        }
        // sign check: the opening turn must swing the forward edge outward (the aft part tucks into the duct)
        var h0 = hinges[0]; var mesh0 = M["revdoor_" + s + "1"]; var vs = mesh0.vertices; var dtr = h0.Find("reverserDoor_" + num + "_1");
        int aft = 0; for (int i = 1; i < vs.Length; i++) if (dtr.TransformPoint(vs[i]).z > dtr.TransformPoint(vs[aft]).z) aft = i;
        var r0 = dtr.TransformPoint(vs[aft]) - axis; r0.z = 0f; float before = r0.magnitude;
        h0.Rotate(new Vector3(10f, 0f, 0f), Space.Self); var r1 = dtr.TransformPoint(vs[aft]) - axis; r1.z = 0f; h0.Rotate(new Vector3(-10f, 0f, 0f), Space.Self);
        float open = r1.magnitude > before ? 32f : -32f;
        log.AppendLine("reversers " + num + " open " + open + " (lower pair " + open / 2 + ")");
        var abType = GameType("Airbrake");
        var donor = AssetDatabase.LoadAssetAtPath<GameObject>(Placeholder("SmallFighter1", "Prefab"));
        var dab = donor == null ? null : donor.GetComponentsInChildren<Component>(true).FirstOrDefault(c => c != null && c.GetType() == abType);
        var dsnd = dab == null ? null : new SerializedObject(dab).FindProperty("airbrakeSound").objectReferenceValue as AudioSource;
        // two stock airbrakes per engine: the upper pair opens fully, the lower pair half as far to stay clear of the ground
        for (int set = 0; set < 2; set++)
        {
            var ab = en.gameObject.AddComponent(abType);
            ObjArray(ab, "transforms", set == 0 ? new Object[] { hinges[0], hinges[3] } : new Object[] { hinges[1], hinges[2] });
            ObjArray(ab, "constraints", aims[set].Cast<Object>().ToArray());
            Set(ab, "maxAngle", set == 0 ? open : open / 2f); Set(ab, "openSpeed", 0.8f); Set(ab, "dragAmount", 3f);
            Set(ab, "part", C(en, "UnitPart") ?? C(en, "AeroPart")); Set(ab, "aircraft", C(root, "Aircraft"));
            Set(ab, "volumeMultiplier", 0.8f); Set(ab, "maxVolumeSpeed", 80f); Set(ab, "pitchMin", 0.4f); Set(ab, "pitchMax", 0.9f);
            if (set == 0 && dsnd != null)
            {
                var sg = New("reverserSound_" + num, en); sg.localPosition = Vector3.zero;
                var src = sg.gameObject.AddComponent<AudioSource>(); EditorUtility.CopySerialized(dsnd, src); src.playOnAwake = false;
                Set(ab, "airbrakeSound", src);
            }
            else if (set == 0) log.AppendLine("no airbrake sound donor");
        }
    }

    // ------------------------------------------------------------------ tail: fixed stabilisers, elevators; the Medusa's twin fins become one fin in two pieces
    static void Tail()
    {
        var tail = Need("tail");
        foreach (var s in new[] { "L", "R" })
        {
            PartAt("hstab_" + s);
            Surface("elevator_" + s, "elevator_" + s + "_hinge", "elevator_" + s + "_visible", "elevator_" + s,
                    P("elevator_" + s + "_hingeA"), P("elevator_" + s + "_hingeB"), null);
            Set(C(Need("elevator_" + s), "AeroPart"), "liftNormal", Need("elevator_" + s + "_hinge"));
            DoomName("slimelight_R" + s);
        }
        var vL = Need("vstab_L"); vL.SetParent(tail, true); PartAt("vstab_L");
        var vR = Need("vstab_R"); vR.SetParent(vL, true); PartAt("vstab_R");
        // each rudder half rides its fin half, so the upper rudder folds with the upper fin in the hangar
        Need("rudder_L").SetParent(vL, true); Need("rudder_R").SetParent(vR, true);
        // 0.3.29: fin fold actuators, cylinder on the lower fin and rod on the upper fin, aimed at each other all the time,
        // so they extend as the plugin folds the upper fin (the same aimed-pair setup as the reverser actuators)
        // 0.4.5: the fold hinge line, read by the plugin (the crank horns now hang below the upper fin's root)
        { var fh = Find(vL, "finFoldHinge") ?? New("finFoldHinge", vL); fh.position = P("fin_hinge"); fh.rotation = Quaternion.identity; }
        for (int k = 1; k <= 2; k++)
        {
            var anc = P("fincyl_" + k); var lug = P("finrod_" + k);
            var cyl = AimedMesh("finFoldActuator_" + k, vL, anc, lug, Vector3.forward, "fincyl_" + k);
            var rodT = AimedMesh("finFoldRod_" + k, vR, lug, anc, Vector3.forward, "finrod_" + k);
            foreach (var a in new[] { Aim(cyl, rodT, vL, Vector3.forward), Aim(rodT, cyl, vL, Vector3.forward) }) ((Behaviour)a).enabled = true;
        }
        foreach (var s in new[] { "L", "R" })
        {
            var vs = Need("vstab_" + s);
            var ln = Need("vstab_" + s + "_liftNormal"); ln.SetParent(vs, true); ln.position = vs.position; ln.rotation = Quaternion.Euler(0f, 0f, 90f);
            var hinge = Need("rudder_" + s + "_hinge"); hinge.SetParent(Need("rudder_" + s), true);
            var a = P("rudder_" + s + "_hingeA"); var b = P("rudder_" + s + "_hingeB");
            Surface("rudder_" + s, "rudder_" + s + "_hinge", "rudder_" + s + "_visible", "rudder_" + s, a, b, null);
            Need("rudder_" + s + "_hinge").rotation = Quaternion.FromToRotation(Vector3.right, (b - a).normalized);
            var vis = Need("rudder_" + s + "_visible"); vis.rotation = Quaternion.identity;
            var rln = Need("rudder_" + s + "_liftNormal"); rln.position = vis.position; rln.rotation = Quaternion.Euler(0f, 0f, 90f);
            Set(C(Need("rudder_" + s), "AeroPart"), "liftNormal", rln);
            Set(C(vs, "AeroPart"), "liftNormal", ln);
        }
    }

    // ------------------------------------------------------------------ 0.4.0 damage pieces (the author 2026-11-02)
    // The fuselage sections (bottom + upper left + upper right; the tail cone in four), the belly fairing (four panels),
    // the cockpit and nose (thirds) and the fin, rudder, stabiliser and elevator tips are parts of their own, cut along
    // notched stock-style seams in p220_split.py. Each piece is an AeroPart under the part it was cut from (the
    // backbone), jointed to everything its hull touches (P220_pieces.json, from hull_touch.py), so a chunk can be shot
    // away without the airframe parting. The tip control surfaces are copies of their surface with the outer mesh.
    static Transform PieceParent(PieceE p)
    {
        if (p.name.StartsWith("elevtip_")) return Need("hstabtip_" + p.name.Substring(8));
        if (p.name == "ruddertip") return Need("fintip");
        return p.of == "fuselage" ? root : Need(p.of);
    }
    static void Pieces()
    {
        string path = ART + "P220_pieces.json";
        if (!System.IO.File.Exists(path)) { log.AppendLine("no damage pieces file"); return; }
        PIECES = JsonUtility.FromJson<PW>("{\"items\":" + System.IO.File.ReadAllText(path) + "}").items.ToList();
        var lg = root.GetComponent<LODGroup>(); var lods = lg.GetLODs();
        var l0 = lods[0].renderers.ToList(); var l1 = lods.Length > 1 ? lods[1].renderers.ToList() : null;
        var apType = C(root, "AeroPart").GetType();
        var lodMats = root.Find("fuselage_lod1").GetComponent<MeshRenderer>().sharedMaterials;
        foreach (var p in PIECES)
        {
            var parent = PieceParent(p);
            if (p.name.StartsWith("elevtip_") || p.name == "ruddertip")
            {
                // a copy of the whole control surface (AeroPart, ControlSurface, hinge, visible mesh, LOD), cut down to the tip
                var src = Need(p.of);
                var go = Object.Instantiate(src.gameObject, parent, true); go.name = p.name;
                foreach (var tr in go.GetComponentsInChildren<Transform>(true)) if (tr != go.transform) tr.name = tr.name.Replace(p.of, p.name);
                var a = P(p.name + "_hingeA"); var b = P(p.name + "_hingeB");
                Surface(p.name, p.name + "_hinge", p.name + "_visible", p.name, a, b, null);
                if (p.name == "ruddertip")
                {
                    Need("ruddertip_hinge").rotation = Quaternion.FromToRotation(Vector3.right, (b - a).normalized);
                    var vis = Need("ruddertip_visible"); vis.rotation = Quaternion.identity;
                    var rln = Find(go.transform, "ruddertip_liftNormal") ?? New("ruddertip_liftNormal", go.transform);
                    rln.position = vis.position; rln.rotation = Quaternion.Euler(0f, 0f, 90f);
                    Set(C(go.transform, "AeroPart"), "liftNormal", rln);
                }
                else Set(C(go.transform, "AeroPart"), "liftNormal", Need(p.name + "_hinge"));
                var r0 = Need(p.name + "_visible").GetComponent<Renderer>(); if (r0 != null) l0.Add(r0);
                var lr = Find(go.transform, p.name + "_lod1"); if (lr != null && l1 != null) l1.Add(lr.GetComponent<Renderer>());
                continue;
            }
            var t = Find(root, p.name) ?? New(p.name, parent);
            t.SetParent(parent, true);
            var tmpl = C(p.of == "fuselage" ? Need("fuselage_F") : Need(p.of), "AeroPart");
            var ap = t.GetComponent(apType) ?? t.gameObject.AddComponent(apType);
            EditorUtility.CopySerialized(tmpl, ap);
            var so = new SerializedObject(ap);
            so.FindProperty("joints").arraySize = 0;
            so.FindProperty("damageMaterial.renderers").arraySize = 0;
            so.FindProperty("disintegrateObjects").arraySize = 0;
            so.FindProperty("criticalPart").boolValue = false;
            so.FindProperty("centerOfMass").objectReferenceValue = null;
            so.FindProperty("connectedAnchor").objectReferenceValue = null;
            so.ApplyModifiedPropertiesWithoutUndo();
            var lod = Find(t, p.name + "_lod1");
            if (lod == null) { lod = New(p.name + "_lod1", t); lod.gameObject.AddComponent<MeshFilter>(); lod.gameObject.AddComponent<MeshRenderer>().sharedMaterials = lodMats; }
            PartAt(p.name);
            // lift direction: tips lift like the surface they came from; fuselage pieces carry no lift
            var tl = Get(tmpl, "liftNormal") as Transform;
            var ln = Find(t, p.name + "_liftNormal") ?? New(p.name + "_liftNormal", t);
            ln.position = t.position; ln.rotation = tl != null ? tl.rotation : Quaternion.identity;
            Set(ap, "liftNormal", ln);
            // 0.4.2: shells collide as thin hulls along their arc (<piece>_seg<k>_colmesh); the whole-piece hull stays the LOD mesh
            {
                var segs = M.Keys.Where(k => k.StartsWith(p.name + "_seg") && k.EndsWith("_colmesh")).OrderBy(k => k.Length).ThenBy(k => k).ToList();
                if (segs.Count > 0)
                {
                    t.GetComponent<MeshCollider>().sharedMesh = M[segs[0]];
                    for (int k = 1; k < segs.Count; k++)
                    {
                        var c = Find(t, p.name + "_col" + k) ?? New(p.name + "_col" + k, t);
                        c.localPosition = Vector3.zero; c.localRotation = Quaternion.identity; c.localScale = Vector3.one;
                        var mc = c.GetComponent<MeshCollider>(); if (mc == null) mc = c.gameObject.AddComponent<MeshCollider>();
                        mc.convex = true; mc.sharedMesh = M[segs[k]];
                    }
                }
            }
            // 0.4.2: on the aircraft layer like the part it came from (new objects start on Default)
            foreach (var c in t.GetComponentsInChildren<Transform>(true)) if (!c.name.EndsWith("_lod1")) c.gameObject.layer = tmpl.gameObject.layer;
            l0.Add(t.GetComponent<Renderer>()); if (l1 != null) l1.Add(lod.GetComponent<Renderer>());
        }
        lods[0].renderers = l0.ToArray(); if (l1 != null) lods[1].renderers = l1.ToArray(); lg.SetLODs(lods);
        // things fitted to a piece ride it: the forward doors, each side's windscreen glass, the dorsal radar mount
        foreach (var s in new[] { "L", "R" })
        {
            Need("doorMount_" + s).SetParent(Need("cockpit_R_sk" + s), true);
            Need("canopy_glass_" + s).SetParent(Need("cockpit_F_sk" + s), true);
            Need("canopy_glass_int_" + s).SetParent(Need("cockpit_F_sk" + s), true);
        }
        Need("dorsalMount").SetParent(Need("fuselage_skR"), true);
        log.AppendLine("damage pieces: " + PIECES.Count + " (" + root.GetComponentsInChildren(apType, true).Length + " parts)");
    }

    // ------------------------------------------------------------------ gear
    static void FitBox(Transform t, Mesh m)
    {
        var b = t.GetComponent<BoxCollider>(); if (b == null) return;
        b.center = m.bounds.center; b.size = m.bounds.size;
    }
    // folds the hinge both ways and keeps the sign that moves the axle toward the wanted direction
    static float FoldSign(Transform hinge, Transform axle, Vector3 want, float deg)
    {
        var rest = hinge.localEulerAngles; var p0 = axle.position;
        hinge.localEulerAngles = rest + new Vector3(deg, 0f, 0f); float a = Vector3.Dot(axle.position - p0, want);
        hinge.localEulerAngles = rest + new Vector3(-deg, 0f, 0f); float b = Vector3.Dot(axle.position - p0, want);
        hinge.localEulerAngles = rest;
        return a >= b ? deg : -deg;
    }
    static void MainGear(string s, float sg)
    {
        var mount = Need("gear_mount_" + s); var hinge = Need("gear_hinge_" + s); var g = Need("gear_" + s);
        mount.position = P("gearHinge_" + s);
        mount.rotation = Quaternion.Euler(0f, 90f, 0f);       // hinge X runs fore and aft: the leg swings sideways
        hinge.localPosition = Vector3.zero; hinge.localRotation = Quaternion.identity;
        g.position = P("gearHinge_" + s); g.rotation = Quaternion.identity;
        g.localScale = Vector3.one;      // the Medusa's right gear is mirrored (-1 x): that flipped the leg door inboard and turned the meshes inside out
        SetMesh(g, "gear_" + s); FitBox(g, M["gear_" + s]);
        float r = 0.58f, travel = 0.55f;
        var axleP = P("axle_" + s);
        var un = Need("gear_" + s + "_unsprung"); un.position = axleP; un.rotation = Quaternion.identity; SetMesh(un, "gear_" + s + "_unsprung");
        var ax = Find(un, "axle"); ax.position = axleP; ax.rotation = Quaternion.identity;
        var w = ax.GetChild(0).name.Contains("wheel") ? ax.GetChild(0) : Find(ax, "EW1_wheel_R");
        w.position = axleP; w.rotation = Quaternion.identity; SetMesh(w, "wheel_" + s);
        var ch = Find(ax, "chocks"); if (ch != null) { ch.position = axleP + new Vector3(0f, -r + 0.02f, 0f); ch.rotation = Quaternion.identity; }
        var bump = Find(g, "bumpstop"); bump.position = axleP + Vector3.up * (travel - r); bump.rotation = Quaternion.identity;
        var cast = Find(g, "castPoint"); if (cast != null) { cast.position = bump.position; cast.rotation = Quaternion.identity; }
        DoomName("gear_" + s + "_arm");
        foreach (var d in new[] { "1", "2", "3" }) { var gd = Find(root, "geardoor_" + s + d); if (gd != null) NoMesh(gd); }
        var lg = C(g, "LandingGear");
        float fold = FoldSign(hinge, ax, new Vector3(-sg, 0.3f, 0f), 80f);   // 80 deg lays the wheels flush in the belly fairing wells
        log.AppendLine("main gear " + s + " foldDegrees " + fold);
        Set(lg, "suspensionTravel", travel); Set(lg, "wheelRadius", r);
        Set(lg, "springRate", 2500000f); Set(lg, "dampingRate", 300000f); Set(lg, "maxCompression", 0.40f);   // breaks at ~4.5x static load, like the stock gear (0.6 never broke: travel is 0.55)
        Set(lg, "contactArea", 0.05f);   // tyre footprint: sets how deep the gear sinks and drags on grass; 0.05 gives a FastBomber-like ground pressure so rough ground breaks it
        // foldSpeed 15 (0.3.14): the aircraft locks the gear up when the FIRST leg finishes, and a main leg (80 deg at 25 deg/s,
        // no doors) used to finish long before the nose leg (105 deg plus 1 s of doors), snapping the nose doors shut early
        Set(lg, "mass", 600f); Set(lg, "foldDegrees", fold); Set(lg, "hingeFoldMotion", Vector3.zero); Set(lg, "foldSpeed", 15f);
        Set(lg, "strutRotation", 0f);   // the Medusa twists its wheels 90 deg as they fold; the P220 well takes them as they are
        Set(lg, "extendedDrag", 4f); Set(lg, "attachedPart", C(Need("wing1b_" + s), "AeroPart"));
        Set(lg, "castPoint", cast); Set(lg, "axle", ax);
        Size(lg, "gearDoors", 0);
        // retraction mechanism, driven by the stock gear's moving parts as the leg folds: a hydraulic actuator (cylinder
        // in the wing root, rod on the leg, each aimed at the other) and a folding side stay (upper link swings up
        // about its wing-root hinge, the lower link on the leg follows its tip, so the knee breaks upward into the wing)
        var fwdAxis = Vector3.forward;
        var aA = P("gearact_cyl_" + s); var aB = P("gearact_rod_" + s);
        var cyl = AimedMesh("gearActuator_" + s, mount, aA, aB, Vector3.up, "gearact_cyl_" + s);
        var rodT = AimedMesh("gearActuatorRod_" + s, g, aB, aA, Vector3.up, "gearact_rod_" + s);
        var S = P("gearstay_up_" + s); var Q = P("gearstay_lo_" + s); var K0 = P("gearstay_knee_" + s);
        float a = (K0 - S).magnitude;
        var fwd0 = (K0 - S).normalized;
        var upBase = New("gearSideStayBase_" + s, mount); upBase.position = S;
        upBase.rotation = Quaternion.LookRotation(fwd0, Vector3.Cross(fwd0, fwdAxis).normalized);   // local X runs fore and aft
        var upT = New("gearSideStayUpper_" + s, upBase); upT.localPosition = Vector3.zero; upT.localRotation = Quaternion.identity;
        var upM = New("gearSideStayUpper_" + s + "_mesh", upT); upM.localRotation = Quaternion.FromToRotation(M["gearstay_up_" + s].bounds.center.normalized, Vector3.forward); SetMesh(upM, "gearstay_up_" + s);
        var knee = New("gearSideStayKnee_" + s, upT); knee.localPosition = new Vector3(0f, 0f, a); knee.localRotation = Quaternion.identity;
        var loT = AimedMesh("gearSideStayLower_" + s, g, Q, K0, Vector3.up, "gearstay_lo_" + s);
        // stowed knee: fold the leg, solve the two-link knee (breaking upward), measure the upper link's swing
        hinge.localEulerAngles = Vector3.right * fold; var Q1 = loT.position; hinge.localRotation = Quaternion.identity;
        var dv = Q1 - S; float h = Mathf.Sqrt(Mathf.Max(a * a - dv.sqrMagnitude / 4f, 0f));
        var nrm = Vector3.Cross(dv, fwdAxis).normalized; if (nrm.y < 0f) nrm = -nrm;
        var K1 = S + dv / 2f + nrm * h;
        float swing = Vector3.SignedAngle(upBase.InverseTransformDirection(K0 - S), upBase.InverseTransformDirection(K1 - S), Vector3.right);
        var so = new SerializedObject(lg); var mp = so.FindProperty("movingParts"); mp.arraySize = 4;
        System.Action<int, Transform, Transform, Vector3> gp = (i, t, tg, fa) =>
        {
            var e = mp.GetArrayElementAtIndex(i);
            e.FindPropertyRelative("transform").objectReferenceValue = t; e.FindPropertyRelative("target").objectReferenceValue = tg;
            e.FindPropertyRelative("foldAngles").vector3Value = fa;
        };
        gp(0, upT, null, new Vector3(swing, 0f, 0f));
        gp(1, loT, knee, Vector3.zero);
        gp(2, cyl, rodT, Vector3.zero);
        gp(3, rodT, cyl, Vector3.zero);
        so.ApplyModifiedPropertiesWithoutUndo();
        log.AppendLine("main gear " + s + " side stay swings " + swing.ToString("F1") + " deg, stowed knee " + K1.ToString("F2") + ", link " + a.ToString("F2"));
    }
    static void NoseGear()
    {
        var hinge = Need("gear_hinge_F"); hinge.position = P("gearHinge_F"); hinge.rotation = Quaternion.identity;
        var mid = Need("EW1_gear_F"); mid.position = P("gearHinge_F"); mid.rotation = Quaternion.identity;
        var g = Need("EW1_gear_F_sprung"); g.position = P("gearHinge_F"); g.rotation = Quaternion.identity;
        SetMesh(g, "gear_F"); FitBox(g, M["gear_F"]);
        float r = 0.36f, travel = 0.45f;
        var axleP = P("axle_F");
        var un = Need("EW1_gear_F_unsprung"); un.position = axleP; un.rotation = Quaternion.identity; SetMesh(un, "gear_F_unsprung");
        var ax = Need("EW1_gear_F_axle"); ax.position = axleP; ax.rotation = Quaternion.identity;
        var w = Need("EW1_wheel_F"); w.position = axleP; w.rotation = Quaternion.identity; SetMesh(w, "wheel_F");
        var ch = Find(ax, "chocks"); if (ch != null) { ch.position = axleP + new Vector3(0f, -r + 0.02f, 0f); ch.rotation = Quaternion.identity; }
        var bump = Find(g, "bumpstop"); bump.position = axleP + Vector3.up * (travel - r); bump.rotation = Quaternion.identity;
        var gl = Find(g, "gearlight_F_mesh"); if (gl != null) { gl.position = P("gearHinge_F") + new Vector3(0f, -0.6f, 0.15f); }
        DoomName("EW1_gear_F_arm"); DoomName("gear_F_armTarget");
        var lg = C(g, "LandingGear");
        float fold = FoldSign(hinge, ax, new Vector3(0f, 0.3f, 1f), 105f);
        log.AppendLine("nose gear foldDegrees " + fold);
        Set(lg, "suspensionTravel", travel); Set(lg, "wheelRadius", r);
        Set(lg, "springRate", 1200000f); Set(lg, "dampingRate", 160000f); Set(lg, "maxCompression", 0.30f); Set(lg, "contactArea", 0.015f);
        Set(lg, "mass", 250f); Set(lg, "foldDegrees", fold); Set(lg, "hingeFoldMotion", Vector3.zero); Set(lg, "foldSpeed", 25f);
        Set(lg, "steeringLock", 60f); Set(lg, "steeringSpeed", 40f); Set(lg, "extendedDrag", 2f);
        Set(lg, "axle", ax); Size(lg, "movingParts", 0);
        // clamshell bay doors: hinge transforms lie along the bay edges (local Z = hinge line); closed is the hinge's zero
        // rotation, as the stock gear code snaps doors to zero once retracted
        var so = new SerializedObject(lg); var gdp = so.FindProperty("gearDoors"); gdp.arraySize = 2;
        int k = 0;
        foreach (var s in new[] { "L", "R" })
        {
            var door = Need("geardoor_F" + s); var dh = door.parent; var mount = dh.parent;
            var a = P("geardoor_F" + s + "_hingeA"); var b = P("geardoor_F" + s + "_hingeB");
            mount.position = (a + b) * 0.5f; mount.rotation = Quaternion.LookRotation((b - a).normalized, Vector3.up);
            dh.localPosition = Vector3.zero; dh.localRotation = Quaternion.identity;
            door.position = P("geardoor_F" + s); door.rotation = Quaternion.identity; door.localScale = Vector3.one;
            SetMesh(door, "geardoor_F" + s);
            var c0 = door.GetComponent<Renderer>().bounds.center;
            dh.localEulerAngles = new Vector3(0f, 0f, 85f); float up1 = door.GetComponent<Renderer>().bounds.center.y;
            dh.localEulerAngles = new Vector3(0f, 0f, -85f); float up2 = door.GetComponent<Renderer>().bounds.center.y;
            dh.localRotation = Quaternion.identity;
            float open = up1 < up2 ? 85f : -85f;
            var e = gdp.GetArrayElementAtIndex(k++);
            e.FindPropertyRelative("transform").objectReferenceValue = dh;
            e.FindPropertyRelative("closedAngle").vector3Value = Vector3.zero;
            e.FindPropertyRelative("openAngle").vector3Value = new Vector3(0f, 0f, open);
            log.AppendLine("nose door " + s + " opens " + open + " (" + door.parent.parent.name + ")");
        }
        so.ApplyModifiedPropertiesWithoutUndo();
    }

    // ------------------------------------------------------------------ everything else the Medusa carried
    static void Misc()
    {
        foreach (var n in new[] { "Downwash_water1", "downwash", "ladder" }) DoomName(n);
        WeaponBay();
        Need("CoM").position = P("CoM");
        Need("contactSparks").position = P("contactSparks");
        var dm = Need("dorsalMount"); dm.position = P("dorsalMount"); dm.rotation = Quaternion.identity;
        var lm = Need("laserMount"); lm.SetParent(Need("tail"), true); lm.position = P("laserMount");
        lm.rotation = LaserRest;   // pod gimbal: turret "up" runs aft along the fuselage (roll stage), "forward" points down (rest)
    }

    // ------------------------------------------------------------------ hardpoints
    // 0.3.29: no AGM-68 or Kingpin rocket pods on the wings
    static readonly string[] WingOptions = { "AAM1_single", "AAM1_double", "AAM2_single", "AAM2_double",
        "ARM1_single", "ARM2_single", "AShM2_single",
        "AShM2_double", "AIR-2_Genie_single", "SpecialSmokePod", "JammingPod1" };   // jamming pod, not the ECM pod (that one is for aircraft without an internal jammer)
    static void HardpointSet(SerializedProperty set, string name, Object[] options, params object[] hp)
    {
        set.FindPropertyRelative("name").stringValue = name;
        set.FindPropertyRelative("precludingHardpointSets").arraySize = 0;
        set.FindPropertyRelative("SymmetryWithPrev").boolValue = false;
        var o = set.FindPropertyRelative("weaponOptions"); o.arraySize = options.Length;
        for (int i = 0; i < options.Length; i++) o.GetArrayElementAtIndex(i).objectReferenceValue = options[i];
        var h = set.FindPropertyRelative("hardpoints"); int n = hp.Length / 2; h.arraySize = n;
        for (int i = 0; i < n; i++)
        {
            var e = h.GetArrayElementAtIndex(i);
            e.FindPropertyRelative("transform").objectReferenceValue = (Transform)hp[2 * i];
            e.FindPropertyRelative("part").objectReferenceValue = (Object)hp[2 * i + 1];
            var py = e.FindPropertyRelative("Pylon"); if (py != null) py.objectReferenceValue = null;
            var pl = e.FindPropertyRelative("Plug"); if (pl != null) pl.objectReferenceValue = null;
            // a hardpoint element added by resizing starts at 0 s, and a 0 s door spring never opens the bay doors
            e.FindPropertyRelative("doorOpenDuration").floatValue = 1f;
        }
    }
    static void Weapons()
    {
        var wm = C(Need("cockpit_F"), "WeaponManager");
        var so = new SerializedObject(wm);
        var sets = so.FindProperty("hardpointSets");
        // the Medusa's internal bay options, read before its set is reused: each side of the rear bay offers the same
        var bayOpts = new List<Object>();
        var bo = sets.GetArrayElementAtIndex(1).FindPropertyRelative("weaponOptions");
        for (int i = 0; i < bo.arraySize; i++) bayOpts.Add(bo.GetArrayElementAtIndex(i).objectReferenceValue);
        var bayDoors = sets.GetArrayElementAtIndex(1).FindPropertyRelative("hardpoints").GetArrayElementAtIndex(0).FindPropertyRelative("bayDoors");
        var doors = new List<Object>(); for (int i = 0; i < bayDoors.arraySize; i++) doors.Add(bayDoors.GetArrayElementAtIndex(i).objectReferenceValue);
        while (sets.arraySize > 6) sets.DeleteArrayElementAtIndex(sets.arraySize - 1);
        while (sets.arraySize < 6) sets.InsertArrayElementAtIndex(sets.arraySize - 1);
        var wing = new List<Object> { null };
        foreach (var n in WingOptions) { try { wing.Add(Mount(n)); } catch (System.Exception ex) { log.AppendLine("wing option skipped: " + ex.Message); } }
        // weapon cycling follows set order: the tail laser goes last
        HardpointSet(sets.GetArrayElementAtIndex(0), "Dorsal Radar", new Object[] { null, Mount("P220_GlobalEye") }, Need("dorsalMount"), AP("fuselage_skR"));   // 0.4.0: rides the upper right centre piece
        HardpointSet(sets.GetArrayElementAtIndex(1), "Wing Pylons", wing.ToArray(), Need("pylon_L1"), AP("wing2_L"), Need("pylon_R1"), AP("wing2_R"));
        HardpointSet(sets.GetArrayElementAtIndex(2), "Bay Left", bayOpts.ToArray(), Need("weaponBayHardpoint"), AP("fuselage_R"));
        HardpointSet(sets.GetArrayElementAtIndex(3), "Bay Right", bayOpts.ToArray(), Need("weaponBayHardpoint_R"), AP("fuselage_R"));

        // the capacitor pack takes the whole rear bay: it and the two bay sides rule each other out
        var hc = Find(root, "weaponBayHardpoint_C"); if (hc == null) hc = New("weaponBayHardpoint_C", Need("weaponBayHardpoint").parent);
        hc.position = (P("bayHardpoint_L") + P("bayHardpoint_R")) * 0.5f; hc.rotation = Quaternion.identity;
        // weapon cycling follows set order: the combined bay, then the tail laser last
        HardpointSet(sets.GetArrayElementAtIndex(4), "Rear Bay (combined)", new Object[] { null, CapPack() }, hc, AP("fuselage_R"));
        HardpointSet(sets.GetArrayElementAtIndex(5), "Tail Laser", new Object[] { null, Mount("P220_laser20") }, Need("laserMount"), AP("tail"));
        System.Action<int, int[]> preclude = (si, others) =>
        {
            var pr = sets.GetArrayElementAtIndex(si).FindPropertyRelative("precludingHardpointSets"); pr.arraySize = others.Length;
            for (int k = 0; k < others.Length; k++) pr.GetArrayElementAtIndex(k).intValue = others[k];
        };
        preclude(2, new[] { 4 }); preclude(3, new[] { 4 }); preclude(4, new[] { 2, 3 }); preclude(5, new int[0]);
        for (int si = 0; si < 6; si++)
        {
            var hps = sets.GetArrayElementAtIndex(si).FindPropertyRelative("hardpoints");
            for (int i = 0; i < hps.arraySize; i++)
            {
                var bd = hps.GetArrayElementAtIndex(i).FindPropertyRelative("bayDoors");
                bool bay = si == 2 || si == 3;   // the capacitor pack never opens the doors
                bd.arraySize = bay ? doors.Count : 0;
                for (int k = 0; bay && k < doors.Count; k++) bd.GetArrayElementAtIndex(k).objectReferenceValue = doors[k];
            }
        }
        so.ApplyModifiedPropertiesWithoutUndo();
        log.AppendLine("hardpoints: laser, capacitor pack, dorsal radar, wing pylons (" + (wing.Count - 1) + " options), bay left/right (" + (bayOpts.Count - 1) + " options, " + doors.Count + " doors)");
    }

    // ------------------------------------------------------------------ mass, lift, drag, fuel, engines, joints
    static void Part(string n, float mass, float area, float drag, float fuel)
    {
        var t = n == "" ? root : Need(n);
        var ap = C(t, "AeroPart");
        Set(ap, "mass", mass); Set(ap, "wingArea", area); Set(ap, "dragArea", drag);
        var ft = C(t, "FuelTank");
        if (ft != null) Set(ft, "fuelCapacity", fuel < 0f ? 0f : fuel);
        else if (fuel > 0f) log.AppendLine("no FuelTank on " + n);
    }
    static void AeroAndDamage()
    {
        // 37.2 t airframe, 12.2 t fuel (stock-like fuel fraction, the real 17 t is more than the game needs); wing area set
        // to stock wing loading (Darkreach ~174 kg/m2, PB-22 ~180 at half fuel) rather than the real 112 m2 wing, and
        // thrust to a Darkreach-like 0.55 thrust/weight
        // plus 7.5 t of mission systems and survivability equipment (40% of the real 18.7 t max payload), spread
        // through the cabin sections: centre +2,000, forward +2,000, rear +2,000, front cabin +1,500
        // 0.4.0 damage pieces: each section's mass is shared out with the pieces cut from it (the totals are unchanged)
        Part("", 5600f, 0f, 0.55f, 5000f);
        Part("fuselage_skL", 600f, 0f, 0f, -1f); Part("fuselage_skR", 600f, 0f, 0f, -1f);
        Part("belly_FL", 300f, 0f, 0f, -1f); Part("belly_FR", 300f, 0f, 0f, -1f); Part("belly_AL", 300f, 0f, 0f, -1f); Part("belly_AR", 300f, 0f, 0f, -1f);
        Part("fuselage_F", 3000f, 0f, 0.15f, 0f);
        Part("fuselage_F_skL", 1000f, 0f, 0f, -1f); Part("fuselage_F_skR", 1000f, 0f, 0f, -1f);
        Part("cockpit_R", 3000f, 0f, 0.2f, -1f);
        Part("cockpit_R_skL", 1000f, 0f, 0f, -1f); Part("cockpit_R_skR", 1000f, 0f, 0f, -1f);
        Part("cockpit_F", 1100f, 0f, 0.15f, -1f);
        Part("cockpit_F_skL", 350f, 0f, 0f, -1f); Part("cockpit_F_skR", 350f, 0f, 0f, -1f);
        Part("nose", 180f, 0f, 0.1f, -1f);
        Part("nose_skL", 60f, 0f, 0f, -1f); Part("nose_skR", 60f, 0f, 0f, -1f);
        Part("fuselage_R", 3300f, 0f, 0.2f, 0f);
        Part("fuselage_R_skL", 1100f, 0f, 0f, -1f); Part("fuselage_R_skR", 1100f, 0f, 0f, -1f);
        Part("tail", 825f, 0f, 0.15f, -1f);
        Part("tail_skL", 225f, 0f, 0f, -1f); Part("tail_skR", 225f, 0f, 0f, -1f); Part("tail_skB", 225f, 0f, 0f, -1f);
        Part("vstab_L", 500f, 10f, 0.03f, -1f); Part("vstab_R", 210f, 4.5f, 0.015f, -1f); Part("fintip", 90f, 1.5f, 0.005f, -1f);
        Part("rudder_L", 120f, 3.6f, 0f, -1f); Part("rudder_R", 70f, 2.2f, 0f, -1f); Part("ruddertip", 30f, 0.8f, 0f, -1f);
        // pieces come away before the sections they hang on: the fuselage shells and belly panels at 15 % health, tips at 10 %
        foreach (var n in new[] { "fuselage_skL", "fuselage_skR", "belly_FL", "belly_FR", "belly_AL", "belly_AR", "fuselage_F_skL", "fuselage_F_skR",
                                  "cockpit_R_skL", "cockpit_R_skR", "cockpit_F_skL", "cockpit_F_skR", "nose_skL", "nose_skR",
                                  "fuselage_R_skL", "fuselage_R_skR", "tail_skL", "tail_skR", "tail_skB" })
            Set(AP(n), "structuralThreshold", 15f);
        foreach (var n in new[] { "fintip", "ruddertip", "hstabtip_L", "hstabtip_R", "elevtip_L", "elevtip_R" }) Set(AP(n), "structuralThreshold", 10f);
        foreach (var s in new[] { "L", "R" })
        {
            // main wing areas cut 20% in 0.3.5: loaded takeoff was ~245 km/h, a heavy A220-300 rotates nearer 270-280
            Part("wing1a_" + s, 900f, 11.6f, 0.05f, 700f);
            Part("wing1b_" + s, 2000f, 28f, 0.12f, 1800f);
            Part("wing2_" + s, 1100f, 17.6f, 0.08f, 900f);
            Part("wing3_" + s, 600f, 10.4f, 0.05f, 200f);
            Part("wingtip_" + s, 120f, 2.8f, 0.02f, -1f);
            Part("flap_" + s, 250f, 10.4f, 0.02f, -1f);
            Part("aileron_" + s, 120f, 5.2f, 0f, -1f);
            Part("intake_" + s, 300f, 0f, 0.03f, -1f);
            Part("engine_" + s, 2300f, 0f, 0.25f, -1f);
            Part("hstab_" + s, 340f, 9f, 0.03f, -1f); Part("hstabtip_" + s, 110f, 3f, 0.01f, -1f);
            Part("elevator_" + s, 115f, 5f, 0f, -1f); Part("elevtip_" + s, 35f, 1.5f, 0f, -1f);
            foreach (var w in new[] { "wing1a_", "wing1b_", "wing2_", "wing3_", "wingtip_", "hstab_", "aileron_", "elevator_", "hstabtip_", "elevtip_" })
                Set(AP(w + s), "centerOfLift", Vector3.zero);
            // flap and aileron lift acts at the wing's quarter chord, not on the hinge line behind the CG
            var fq = (P("wing1b_" + s) + P("wing2_" + s)) * 0.5f;
            Set(AP("flap_" + s), "centerOfLift", fq - Need("flap_" + s).position);
            Set(AP("aileron_" + s), "centerOfLift", P("wing3_" + s) - Need("aileron_" + s).position);
            var tj = C(Need("engine_" + s), "Turbojet");
            Set(tj, "maxThrust", 125000f); Set(tj, "maxSpeed", 300f);
            Set(tj, "fuelConsumptionMin", 0.043f); Set(tj, "fuelConsumptionMax", 0.30f);   // 0.4.15: kg/s per engine (game draws it once a second, lerped by thrust ratio); was 0.2/1.4, which burned ~45 lb/nmi at cruise against a real A220 ~9.65 lb/nmi (~2,100 kg/h for both engines)
            Set(tj, "failureMessage", s == "L" ? "LEFT ENGINE FIRE" : "RIGHT ENGINE FIRE");
            Set(C(Need("nozzle_R" + s), "JetNozzle"), "IRMax", 4f);
            var el = C(Need("elevator_" + s), "ControlSurface"); Set(el, "pitchRange", -17f); Set(el, "servoSpeed", 40f);   // pitch range was -25: pulled turns too hard (the author 2026-11-01)
            var et = C(Need("elevtip_" + s), "ControlSurface"); Set(et, "pitchRange", -17f); Set(et, "servoSpeed", 40f);
            var ai = C(Need("aileron_" + s), "ControlSurface"); Set(ai, "rollRange", s == "L" ? -26f : 26f); Set(ai, "servoSpeed", 50f);
        }
        foreach (var n in new[] { "rudder_L", "rudder_R", "ruddertip" }) { var ru = C(Need(n), "ControlSurface"); Set(ru, "yawRange", -28f); Set(ru, "servoSpeed", 35f); }
        root.GetComponent<Rigidbody>().mass = 44700f;

        // joints: every part to its structural neighbours (jointed hulls may overlap; unjointed ones must not)
        // every fuselage section is held by its neighbour and by the section beyond it, so the long body stays stiff
        // instead of flexing at each single joint (the PB-22 layout)
        // 0.4.2 (one Anvil 57 mm round broke the fuselage apart; wants 2 to 3 hits): fuselage joints x2.5
        Joints("nose", "cockpit_F", 262500f, "cockpit_R", 175000f);
        Joints("cockpit_F", "cockpit_R", 1050000f, "fuselage_F", 700000f);
        Joints("cockpit_R", "fuselage_F", 1400000f, root.name, 875000f);
        Joints("fuselage_F", root.name, 1750000f, "fuselage_R", 875000f);
        Joints("fuselage_R", root.name, 1750000f);
        Joints("tail", "fuselage_R", 1050000f, root.name, 525000f);
        // 0.4.0: tail surface roots very strong, weaker towards the tips
        Joints("vstab_L", "tail", 900000f, "fuselage_R", 300000f);
        Joints("vstab_R", "vstab_L", 2000000f);   // 0.4.5 (flight loads broke the fin at the hinge): was 600k
        // 0.4.6 (the upper rudder stopped responding while taxiing, then the upper fin broke off): each rudder half
        // touched the other fin half at the split without a joint between them, so the two bodies rubbed and the light
        // upper rudder took contact damage. A joint between them stops that contact; the upper rudder is held harder.
        Joints("rudder_L", "vstab_L", 250000f, "tail", 80000f, "vstab_R", 80000f);
        Joints("rudder_R", "vstab_R", 300000f, "rudder_L", 100000f, "vstab_L", 80000f);
        foreach (var s in new[] { "L", "R" })
        {
            Joints("hstab_" + s, "tail", 700000f);
            Joints("elevator_" + s, "hstab_" + s, 250000f, "tail", 80000f);
            // wing joints solve at 12 iterations like the PB-22's outer wing (less flex under load), and every outer
            // panel is also held by the panel beyond its neighbour, like the fuselage, so the span bends as one piece
            jointIterations = 12;
            // 0.4.0: wing roots very strong, each panel weaker than the one inboard of it
            Joints("wing1a_" + s, root.name, 2500000f);
            Joints("wing1b_" + s, "wing1a_" + s, 2000000f, root.name, 1200000f);
            Joints("wing2_" + s, "wing1b_" + s, 1400000f, "wing1a_" + s, 600000f);
            Joints("wing3_" + s, "wing2_" + s, 800000f, "wing1b_" + s, 300000f);
            Joints("wingtip_" + s, "wing3_" + s, 250000f, "wing2_" + s, 80000f);
            Joints("flap_" + s, "wing2_" + s, 1000000f, "wing1b_" + s, 1000000f, "wing1a_" + s, 500000f, root.name, 250000f);
            Joints("aileron_" + s, "wing3_" + s, 500000f, "wing2_" + s, 200000f);
            jointIterations = 6;
            Joints("intake_" + s, "wing1b_" + s, 600000f);
            Joints("engine_" + s, "intake_" + s, 500000f, "wing1b_" + s, 300000f);
        }
        // damage pieces: held hardest by the part they were cut from, then by every other part their hull touches
        jointIterations = 6;
        foreach (var p in PIECES)
        {
            bool tip = p.name.Contains("tip");
            float own = p.name.StartsWith("belly_") ? 350000f : p.name == "hstabtip_L" || p.name == "hstabtip_R" ? 200000f : p.name == "fintip" ? 150000f
                      : p.name.StartsWith("elevtip_") || p.name == "ruddertip" ? 80000f : 437500f;
            var pairs = new List<object> { p.of == "fuselage" ? root.name : p.of, own };
            foreach (var o in p.touch)
            {
                if (o == p.of) continue;
                pairs.Add(o == "fuselage" ? root.name : o); pairs.Add(tip ? 40000f : 210000f);
            }
            Joints(p.name, pairs.ToArray());
        }
        // 0.4.4: fuselage, cockpit and nose pieces copy the Darkreach armour; tail pieces back to the Medusa values.
        // Wings, engines and surfaces keep the Medusa values they inherited. Literal values.
        {
            var armor = new Dictionary<string, float[]>   // { pierceArmor, pierceTolerance, blastTolerance }
            {
                { root.name, new[] { 15f, 20f, 5f } },
                { "fuselage_skL", new[] { 15f, 20f, 5f } }, { "fuselage_skR", new[] { 15f, 20f, 5f } },
                { "belly_FL", new[] { 15f, 20f, 5f } }, { "belly_FR", new[] { 15f, 20f, 5f } }, { "belly_AL", new[] { 15f, 20f, 5f } }, { "belly_AR", new[] { 15f, 20f, 5f } },
                { "fuselage_F", new[] { 15f, 20f, 5f } }, { "fuselage_F_skL", new[] { 15f, 20f, 5f } }, { "fuselage_F_skR", new[] { 15f, 20f, 5f } },
                { "fuselage_R", new[] { 15f, 20f, 5f } }, { "fuselage_R_skL", new[] { 15f, 20f, 5f } }, { "fuselage_R_skR", new[] { 15f, 20f, 5f } },
                { "cockpit_R", new[] { 15f, 20f, 5f } }, { "cockpit_R_skL", new[] { 15f, 20f, 5f } }, { "cockpit_R_skR", new[] { 15f, 20f, 5f } },
                { "cockpit_F", new[] { 15f, 20f, 5f } }, { "cockpit_F_skL", new[] { 15f, 20f, 5f } }, { "cockpit_F_skR", new[] { 15f, 20f, 5f } },
                { "nose", new[] { 10f, 5f, 2.5f } }, { "nose_skL", new[] { 10f, 5f, 2.5f } }, { "nose_skR", new[] { 10f, 5f, 2.5f } },
                { "tail", new[] { 30f, 6f, 2f } }, { "tail_skL", new[] { 30f, 6f, 2f } }, { "tail_skR", new[] { 30f, 6f, 2f } }, { "tail_skB", new[] { 30f, 6f, 2f } },
            };
            // 0.4.11 (still too tough against Anvil 57 mm airbursts): fuselage, belly and root blastArmor 70 -> 60,
            // cockpit 80 -> 70, and their blastTolerance 5 -> 4. Nose and tail pieces unchanged.
            foreach (var kv in armor)
            {
                var t = kv.Key == root.name ? root : Need(kv.Key);
                var so = new SerializedObject(C(t, "AeroPart"));
                so.FindProperty("armorProperties.pierceArmor").floatValue = kv.Value[0];
                so.FindProperty("armorProperties.pierceTolerance").floatValue = kv.Value[1];
                bool body = !kv.Key.StartsWith("nose") && !kv.Key.StartsWith("tail");
                so.FindProperty("armorProperties.blastTolerance").floatValue = body ? 4f : kv.Value[2];
                if (body) so.FindProperty("armorProperties.blastArmor").floatValue = kv.Key.StartsWith("cockpit") ? 70f : 60f;
                so.ApplyModifiedPropertiesWithoutUndo();
            }
        }
        // centre of mass report: parts at their hull centres plus half fuel
        float m = 0f; Vector3 sum = Vector3.zero;
        foreach (var ap in root.GetComponentsInChildren<Component>(true).Where(c => c != null && c.GetType().Name == "AeroPart"))
        {
            var so = new SerializedObject(ap); float pm = so.FindProperty("mass").floatValue;
            var ft = C(ap.transform, "FuelTank"); if (ft != null) pm += 0.5f * new SerializedObject(ft).FindProperty("fuelCapacity").floatValue;
            var mc = ap.GetComponent<MeshCollider>(); var c = mc != null && mc.sharedMesh != null ? ap.transform.TransformPoint(mc.sharedMesh.bounds.center) : ap.transform.position;
            m += pm; sum += pm * c;
        }
        var com = sum / m;
        log.AppendLine("mass " + m.ToString("F0") + " kg (half fuel), CoM z " + com.z.ToString("F2") + " y " + com.y.ToString("F2") + "; main axles z " + P("axle_L").z.ToString("F2") + ", nose axle z " + P("axle_F").z.ToString("F2"));
    }

    // ------------------------------------------------------------------ mounts: 20 kW pulse laser (Spearhead), GlobalEye dorsal radar
    static GameObject CopyPrefab(string src, string dst)
    {
        var tmp = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Placeholder(src, "GameObject")));
        PrefabUtility.UnpackPrefabInstance(tmp, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
        tmp.name = dst; return tmp;
    }
    static Object SaveMount(GameObject go, string key, string copyFrom, Object info, string mountName)
    {
        var pf = PrefabUtility.SaveAsPrefabAsset(go, MNT + key + ".prefab");
        string mpath = MNT + key + ".asset";
        var m = AssetDatabase.LoadMainAssetAtPath(mpath);
        if (m == null)
        {
            var srcPath = AssetDatabase.FindAssets(copyFrom + "_PLACEHOLDER").Select(AssetDatabase.GUIDToAssetPath)
                .First(p => System.IO.Path.GetFileNameWithoutExtension(p) == copyFrom + "_PLACEHOLDER" && p.EndsWith(".asset") && AssetDatabase.GetMainAssetTypeAtPath(p).Name == "WeaponMount");
            AssetDatabase.CopyAsset(srcPath, mpath); AssetDatabase.ImportAsset(mpath);
            m = AssetDatabase.LoadMainAssetAtPath(mpath);
        }
        var so = new SerializedObject(m);
        so.FindProperty("prefab").objectReferenceValue = pf;
        so.FindProperty("jsonKey").stringValue = key;
        if (info != null) so.FindProperty("info").objectReferenceValue = info;
        so.FindProperty("mountName").stringValue = mountName;
        so.ApplyModifiedPropertiesWithoutUndo();
        EditorUtility.SetDirty(m);
        log.AppendLine("mount " + key + " (" + mountName + ") from " + copyFrom);
        return m;
    }
    // the THORN's own WeaponInfo (a copy of the stock point-defence laser's, renamed) so the HUD and loadout name it
    static Object ThornInfo()
    {
        string path = MNT + "P220_thornInfo.asset";
        if (AssetDatabase.LoadMainAssetAtPath(path) == null) { AssetDatabase.CopyAsset(Placeholder("Laser_APS1", "WeaponInfo"), path); AssetDatabase.ImportAsset(path); }
        var info = AssetDatabase.LoadMainAssetAtPath(path);
        var so = new SerializedObject(info);
        so.FindProperty("weaponName").stringValue = "THORNE Airborne Laser";
        so.FindProperty("shortName").stringValue = "THORNE";
        so.FindProperty("description").stringValue = "A 80-kilowatt hardkill laser pod mounted on the tail cone. It burns down incoming missiles and draws hard on the capacitor while it fires. Its arc covers everything below and behind the aircraft. Roll the belly towards an incoming missile for the widest field of fire. Can be manually controlled or trusted to a gunner.";
        so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(info);
        return info;
    }
    // the capacitor pack's own WeaponInfo (a copy of the stock fuel container's, renamed): name and loadout description only
    static Object CapInfo()
    {
        string path = MNT + "P220_capInfo.asset";
        if (AssetDatabase.LoadMainAssetAtPath(path) == null) { AssetDatabase.CopyAsset(Placeholder("FuelContainer1_info", "WeaponInfo"), path); AssetDatabase.ImportAsset(path); }
        var info = AssetDatabase.LoadMainAssetAtPath(path);
        var so = new SerializedObject(info);
        so.FindProperty("weaponName").stringValue = "Capacitor Pack";
        so.FindProperty("shortName").stringValue = "CAP PACK";
        so.FindProperty("description").stringValue = "A rack of extra capacitor banks that fills the whole rear weapons bay and wires into the THORNE tail laser. It adds 75% to the laser's capacitor, so the laser can keep burning down missiles for longer before it has to recharge. Weighs 450 kg and leaves no room for weapons in the bay.";
        so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(info);
        return info;
    }
    // capacitor pack: fills the whole rear bay, adds 75% to the capacitor (the plugin adds 525 when it is fitted).
    // No weapon and no WeaponInfo, like the stock tail hook mounts, so it never joins the weapon cycle
    static Object CapPack()
    {
        var go = new GameObject("P220_capPack");
        try
        {
            var m = SaveMount(go, "P220_capPack", "TailHook_Multirole1", null, "Capacitor Pack");
            var so = new SerializedObject(m);
            // 0.3.27: a WeaponInfo for the loadout description, the way the stock fuel containers carry one
            so.FindProperty("info").objectReferenceValue = CapInfo();
            so.FindProperty("tailHook").boolValue = false;
            so.FindProperty("ammo").intValue = 0;
            so.FindProperty("mass").floatValue = 450f; so.FindProperty("emptyMass").floatValue = 450f;
            so.FindProperty("emptyCost").floatValue = 1.2f;
            so.FindProperty("drag").floatValue = 0f; so.FindProperty("emptyDrag").floatValue = 0f;
            so.FindProperty("RCS").floatValue = 0f; so.FindProperty("emptyRCS").floatValue = 0f;
            so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(m);
            return m;
        }
        finally { Object.DestroyImmediate(go); }
    }
    static void Mounts()
    {
        // laser: the Spearhead's own defensive laser turret. onlyDefensive means it only engages missiles aimed at this
        // aircraft; it is cued by the aircraft's sensors (parentUnitTargetDetector) and traverses 135 deg either side of
        // the tail for a 270 deg rear arc. The Medusa laser it replaces had no turret, so nothing ever told it to fire.
        var mbt = CopyPrefab("MBT1", "mbt_tmp");
        var go = new GameObject("P220_laser20");
        try
        {
            var lt = mbt.GetComponentsInChildren<Transform>(true).First(t => t.name == "laser_turret");
            lt.SetParent(go.transform, false); lt.localPosition = Vector3.zero; lt.localRotation = Quaternion.identity;
            var tur = C(lt, "Turret");
            Set(tur, "attachedUnit", null); Set(tur, "targetAcquisitionMode", 0);
            Size(tur, "targetDetectors", 0); Size(tur, "criticalParts", 0);
            // pod-style gimbal: the turret traverse is the roll stage about the fuselage axis (full 360), the elevation
            // tilts the ball from straight aft (-90, the rest pose the plugin returns it to) through straight down (0) to
            // 5 deg below the horizon ahead (+85)
            Set(tur, "traverseRange", 360f); Set(tur, "traverseRate", 360f);
            Set(tur, "minElevation", -85f); Set(tur, "maxElevation", 90f); Set(tur, "elevationRate", 180f);
            // firing arc: one stock inclusion cone, 125 deg around a line 50 deg below the tail. That covers the whole
            // belly hemisphere down to 5 deg below the horizon ahead, the sides to 35 deg above the horizon and aft to
            // 75 deg up, but not the top of the aircraft: turn the belly to the missile to give the laser the widest arc
            var cone = new GameObject("laser_arcCone").transform; cone.SetParent(go.transform, false);
            cone.localPosition = Vector3.zero;
            cone.localRotation = Quaternion.LookRotation(new Vector3(0f, Mathf.Cos(50f * Mathf.Deg2Rad), Mathf.Sin(50f * Mathf.Deg2Rad)), Vector3.right);
            // 0.4.12: the ball must not be able to aim into the airframe. A stock exclusion cone (as stock turrets
            // use) 83 deg around a line 24 deg above straight ahead. Fitted to a ray sweep from the ball against the
            // P220's colliders: every direction the beam would hit the tail cone, stabilisers or wing is inside it with
            // at least 1 deg to spare (blocked directions reach ~81.5 deg off that line at the stabiliser tips). The turret then never points there,
            // never picks targets there and the HUD shows OUT OF ARC for them.
            var noGo = new GameObject("laser_airframeCone").transform; noGo.SetParent(go.transform, false);
            noGo.localPosition = Vector3.zero;
            noGo.localRotation = Quaternion.LookRotation(new Vector3(0f, -Mathf.Cos(24f * Mathf.Deg2Rad), -Mathf.Sin(24f * Mathf.Deg2Rad)), Vector3.right);
            var tso = new SerializedObject(tur); var fcs = tso.FindProperty("firingCones"); fcs.arraySize = 2;
            fcs.GetArrayElementAtIndex(0).FindPropertyRelative("transform").objectReferenceValue = cone;
            fcs.GetArrayElementAtIndex(0).FindPropertyRelative("coneAngle").floatValue = 125f;
            fcs.GetArrayElementAtIndex(0).FindPropertyRelative("exclusion").boolValue = false;
            fcs.GetArrayElementAtIndex(1).FindPropertyRelative("transform").objectReferenceValue = noGo;
            fcs.GetArrayElementAtIndex(1).FindPropertyRelative("coneAngle").floatValue = 83f;
            fcs.GetArrayElementAtIndex(1).FindPropertyRelative("exclusion").boolValue = true;
            tso.ApplyModifiedPropertiesWithoutUndo();
            Object.DestroyImmediate(C(lt, "TargetDetector"));
            Object.DestroyImmediate(lt.GetComponent<SphereCollider>());
            Object.DestroyImmediate(C(lt, "UnitPart"));
            var lz = C(lt.Find("laser_barrel"), "Laser");
            Set(lz, "attachedUnit", null);
            Set(lz, "vehicularPowerSupply", false);
            // THORNE (text says 80 kW): the Medusa laser's damage (40 fire, falling off to nothing at 15 km) at 35% more capacitor draw
            Set(lz, "power", 162f);   // 35% over the Medusa laser's 120 (was +60% in 0.3.4-0.3.7; too weak)
            // beam 60% thicker than the tank laser's; Laser reads its beam width from this scale at start
            var beam = new SerializedObject(lz).FindProperty("beamRenderer").objectReferenceValue as Renderer;
            if (beam != null) { var bs = beam.transform.localScale; beam.transform.localScale = new Vector3(bs.x * 1.6f, bs.y * 1.6f, bs.z); log.AppendLine("laser beam scale " + beam.transform.localScale); } Set(lz, "fireDamage", 40f); Set(lz, "trackingRate", 120f);
            Set(lz, "damageAtRange", new AnimationCurve(new Keyframe(0f, 1f), new Keyframe(15000f, 0f)));   // draw from the aircraft's capacitor like the Medusa laser
            // P220 turret model: the yoke (hubs on the vertical axis) traverses, the spherical head with its flat glass
            // emitter window tilts in it
            // meshes are modelled in aircraft axes at the rest pose; hang them under the gimbal stages with the inverse
            // of the mount's rest rotation
            var inv = Quaternion.Inverse(LaserRest);
            NoMesh(lt); var ym = New("laser_rollStage", lt); ym.localPosition = Vector3.zero; ym.localRotation = inv; SetMesh(ym, "laser_yoke");
            // the scooped hood round the ball belongs to the laser: fixed to the mount, not to the gimbal
            var hood = New("laser_housing", go.transform); hood.localPosition = Vector3.zero; hood.localRotation = inv; SetMesh(hood, "laser_hood");
            var lb = lt.Find("laser_barrel"); lb.localPosition = Vector3.zero; lb.localRotation = Quaternion.Euler(-90f, 0f, 0f);   // rest: straight aft
            NoMesh(lb); var hm = New("laser_ball", lb); hm.localPosition = Vector3.zero; hm.localRotation = inv; SetMesh(hm, "laser_head");
            var aim = lb.Find("aimTransform"); aim.localPosition = new Vector3(0f, 0f, 0.31f); aim.localRotation = Quaternion.identity;
            var info = ThornInfo();
            Set(lz, "info", info);
            Skinnable(go, hood.GetComponent<Renderer>());   // the hood takes the livery like the airframe (stock ColorableMount)
            var m = SaveMount(go, "P220_laser20", "laser_EW1", info, "THORNE Airborne Laser");
            Set(m, "turret", true);
            log.AppendLine("laser turret: " + string.Join(", ", go.GetComponentsInChildren<Component>(true).Select(c => c.GetType().Name)));
        }
        finally { Object.DestroyImmediate(go); Object.DestroyImmediate(mbt); }
        // GlobalEye: the Medusa radome mount (radar values kept) with a fixed Erieye beam instead of the rotodome
        go = CopyPrefab("Radome1", "P220_GlobalEye");
        try
        {
            var rd = go.transform.Find("Radome");
            rd.localPosition = Vector3.zero; rd.localRotation = Quaternion.identity;
            var mf = rd.GetComponent<MeshFilter>(); mf.sharedMesh = M["globaleye"];
            rd.GetComponent<MeshRenderer>().sharedMaterials = new[] { MAT["P220_skin"] };
            var mc = rd.GetComponent<MeshCollider>(); if (mc != null) Object.DestroyImmediate(mc, true);
            // 0.4.3: box over the beam only; the hull of beam + struts reached 6-15 cm into the top shells and damaged them at spawn
            var bc = rd.GetComponent<BoxCollider>(); if (bc == null) bc = rd.gameObject.AddComponent<BoxCollider>();
            bc.center = new Vector3(0f, 1.06f, 0f); bc.size = new Vector3(0.62f, 0.96f, 8.0f);
            var sp = go.transform.Find("spinner");
            var radar = C(go.transform, "Radar");
            var rso = new SerializedObject(radar);
            var rot = rso.FindProperty("rotators");
            log.AppendLine("radar rotators: " + rot.propertyType + (rot.isArray ? " [" + rot.arraySize + "]" : ""));
            if (rot.isArray) rot.arraySize = 0;
            else
            {
                var it = rot.Copy(); var end = rot.GetEndProperty(); it.NextVisible(true);
                while (!SerializedProperty.EqualContents(it, end))
                {
                    if (it.isArray) { log.AppendLine("  rotators." + it.name + " cleared"); it.arraySize = 0; }
                    else if (it.propertyType == SerializedPropertyType.ObjectReference) it.objectReferenceValue = null;
                    if (!it.NextVisible(false)) break;
                }
            }
            rso.ApplyModifiedPropertiesWithoutUndo();
            if (sp != null) Object.DestroyImmediate(sp.gameObject);
            Skinnable(go, rd.GetComponent<Renderer>());   // Medusa listed the radome as colorable (tint only); ours is livery-mapped
            SaveMount(go, "P220_GlobalEye", "Radome1", null, "SpectralEye AEW Radar");
        }
        finally { Object.DestroyImmediate(go); }
    }

    // 0.4.16: the Medusa's VTOL helpers come off, so the P220 handles like the stock conventional jets (Darkreach, Revoker,
    // trainer all have them off): no auto hover (it was the only thing on the P220 that read the custom axis), no hover
    // autopilot, and no Medusa reverse-thrust landing logic (the AI pushed the throttle up on the rollout, which shut the
    // P220's reversers, which open at idle). The fly-by-wire stays, as on every stock jet.
    static void FlightControls()
    {
        var cf = root.GetComponentsInChildren<Component>(true).FirstOrDefault(c => c != null && c.GetType().Name == "ControlsFilter");
        Set(cf, "autoHover.Enabled", false); Set(cf, "autoHover.Active", false); Set(cf, "aimAssist.Enabled", false);
        Set(cf, "ReverseThrust", false);
        var ap = root.GetComponentsInChildren<Component>(true).FirstOrDefault(c => c != null && c.GetType().Name == "AutopilotPlane");
        Set(ap, "hoverController.Enabled", false);
        log.AppendLine("flight controls: auto hover, hover autopilot and Medusa reverse-thrust landing off");
    }

    // 0.4.14 (bay doors stayed demonstrator green, slats/flaps/spoilers stayed white on other liveries): the game
    // writes the livery texture only into renderers listed in a part's damageMaterial.renderers (a part with an empty list
    // gets just its own renderer), so every P220_skin renderer that is not a part itself is added to its owning part.
    static void SkinRegister()
    {
        var listed = new HashSet<Renderer>(); var parts = new List<Component>();
        foreach (var c in root.GetComponentsInChildren<Component>(true))
        {
            if (c == null) continue; bool up = false;
            for (var b = c.GetType(); b != null; b = b.BaseType) if (b.Name == "UnitPart") { up = true; break; }
            if (!up) continue; parts.Add(c);
            var so = new SerializedObject(c); var p = so.FindProperty("damageMaterial.renderers"); if (p == null) continue;
            for (int i = 0; i < p.arraySize; i++) { var r = p.GetArrayElementAtIndex(i).objectReferenceValue as Renderer; if (r != null) listed.Add(r); }
        }
        int added = 0;
        foreach (var r in root.GetComponentsInChildren<Renderer>(true))
        {
            var sm = r.sharedMaterials; if (sm.Length == 0 || sm[0] == null || sm[0].name != "P220_skin" || listed.Contains(r)) continue;
            Component owner = null;
            for (var t = r.transform; t != null && owner == null; t = t.parent)
                foreach (var c in parts) if (c.transform == t) { owner = c; break; }
            if (owner == null) { log.AppendLine("skin renderer without part: " + r.name); continue; }
            if (owner.transform == r.transform) continue;   // a part's own renderer is picked up by the game when its list is empty
            var so = new SerializedObject(owner); var p = so.FindProperty("damageMaterial.renderers");
            if (p.arraySize == 0) { var own = owner.GetComponent<Renderer>(); if (own != null) { p.arraySize = 1; p.GetArrayElementAtIndex(0).objectReferenceValue = own; listed.Add(own); } }
            p.arraySize++; p.GetArrayElementAtIndex(p.arraySize - 1).objectReferenceValue = r; so.ApplyModifiedPropertiesWithoutUndo();
            listed.Add(r); added++;
        }
        log.AppendLine("livery renderers added to parts: " + added);
    }

    static void Skinnable(GameObject go, params Renderer[] rs)
    {
        var cm = C(go.transform, "ColorableMount");
        if (cm == null)
        {
            System.Type ct = null;
            foreach (var a in System.AppDomain.CurrentDomain.GetAssemblies()) { ct = a.GetType("ColorableMount"); if (ct != null) break; }
            cm = go.AddComponent(ct);
        }
        ObjArray(cm, "colorableRenderers"); ObjArray(cm, "skinnableRenderers", rs);
    }

    // ------------------------------------------------------------------ damage diagram: copy of the Medusa status display with the P220 planform.
    // UI/P220_status.png is the outline, UI/P220_status_<part>.png one full-frame fill per AeroPart (named exactly as the part, which is
    // how the stock StatusDisplay ties an image to a part). Sprites come from the top-down part masks (ui/mk.py), drawn in UI/order.txt order.
    static GameObject StatusDisplayP220()
    {
        string ui = MOD + "UI/", dst = ui + "P220_StatusDisplay.prefab";
        string orderPath = System.IO.Path.GetFullPath(ui + "order.txt");
        if (!System.IO.File.Exists(orderPath)) { log.AppendLine("status display: no UI/order.txt"); return null; }
        var order = System.IO.File.ReadAllLines(orderPath).Where(l => l.Trim().Length > 0).Select(l => l.Trim()).ToArray();
        System.Func<string, Sprite> Spr = n =>
        {
            string path = ui + n + ".png";
            var ti = (TextureImporter)AssetImporter.GetAtPath(path);
            if (ti == null) return null;
            ti.textureType = TextureImporterType.Sprite; ti.spriteImportMode = SpriteImportMode.Single; ti.alphaIsTransparency = true;
            ti.mipmapEnabled = false; ti.maxTextureSize = 2048; ti.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<Sprite>(path);
        };
        AssetDatabase.DeleteAsset(dst);
        if (!AssetDatabase.CopyAsset(PH + "GameObject/StatusDisplay_EW1_PLACEHOLDER.prefab", dst)) { log.AppendLine("status display copy failed"); return null; }
        var go = PrefabUtility.LoadPrefabContents(dst);
        try
        {
            go.name = "P220_StatusDisplay";
            const float S = 280f;
            var rt0 = (RectTransform)go.transform; rt0.sizeDelta = new Vector2(S, S);
            var bg = go.GetComponent<UnityEngine.UI.Image>(); bg.sprite = Spr("P220_status");
            var sd = go.GetComponents<Component>().First(c => c != null && c.GetType().Name == "StatusDisplay");
            var so = new SerializedObject(sd);
            // red thresholds from the Medusa entries where the part existed there
            var thr = new Dictionary<string, float>();
            var arr = so.FindProperty("statusDisplays");
            for (int i = 0; i < arr.arraySize; i++)
            {
                var e = arr.GetArrayElementAtIndex(i); var im = e.FindPropertyRelative("partImage").objectReferenceValue as Component;
                if (im != null) thr[im.name] = e.FindPropertyRelative("redStatusThreshold").floatValue;
            }
            float dflt = thr.Count > 0 ? thr.Values.Average() : 0.5f;
            if (thr.ContainsKey("EW1")) thr["P220Primrose"] = thr["EW1"];
            // the Medusa part images go; fire indicators stay
            foreach (Transform ch in go.transform.Cast<Transform>().ToArray()) if (!ch.name.Contains("FIRE")) Object.DestroyImmediate(ch.gameObject);
            arr.arraySize = order.Length;
            for (int i = 0; i < order.Length; i++)
            {
                var n = order[i];
                var c = new GameObject(n, typeof(RectTransform), typeof(CanvasRenderer), typeof(UnityEngine.UI.Image));
                c.layer = go.layer; var rt = (RectTransform)c.transform; rt.SetParent(go.transform, false);
                rt.anchorMin = rt.anchorMax = rt.pivot = new Vector2(0.5f, 0.5f); rt.anchoredPosition = Vector2.zero; rt.sizeDelta = new Vector2(S, S);
                rt.SetSiblingIndex(i);
                var im = c.GetComponent<UnityEngine.UI.Image>(); im.sprite = Spr("P220_status_" + n); im.raycastTarget = false; im.color = new Color(1f, 1f, 0f, 1f);   // stock part colour: yellow; the game lowers green with HP, so damage reads yellow, orange, red
                var e = arr.GetArrayElementAtIndex(i);
                e.FindPropertyRelative("partImage").objectReferenceValue = im;
                e.FindPropertyRelative("redStatusThreshold").floatValue = thr.ContainsKey(n) ? thr[n] : dflt;
            }
            so.ApplyModifiedPropertiesWithoutUndo();
            // engine fire bars on the nacelles (pixel centres from the engine masks, 512 px frame)
            foreach (var f in go.transform.Cast<Transform>().Where(t => t.name.Contains("ENGINE FIRE")).ToArray())   // ToArray: SetAsLastSibling below reorders the children mid-loop
            {
                bool left = f.name.StartsWith("LEFT");
                var rt = (RectTransform)f; float px = left ? 187.5f : 323.5f;
                rt.anchoredPosition = new Vector2((px/512f - 0.5f)*S, (0.5f - 196f/512f)*S);
                rt.localScale = Vector3.one; rt.sizeDelta = new Vector2(20f/512f*S, 36f/512f*S);
                rt.SetAsLastSibling();
                var tx = rt.GetComponentsInChildren<RectTransform>(true).FirstOrDefault(t => t != rt);
                if (tx != null) { tx.localScale = new Vector3(0.5f, 0.5f, 1f); tx.anchoredPosition = new Vector2(left ? -40f : 40f, -32f); }
            }
            PrefabUtility.SaveAsPrefabAsset(go, dst);
            log.AppendLine("status display: " + order.Length + " parts, default red threshold " + dflt.ToString("F2"));
        }
        finally { PrefabUtility.UnloadPrefabContents(go); }
        return AssetDatabase.LoadAssetAtPath<GameObject>(dst);
    }

    // ------------------------------------------------------------------ definition, parameters, hangar op
    static void Assets()
    {
        var pf = AssetDatabase.LoadAssetAtPath<GameObject>(DST);
        var par = AssetDatabase.LoadMainAssetAtPath(PAR);
        var so = new SerializedObject(par);
        so.FindProperty("aircraftName").stringValue = "P220 Primrose";
        so.FindProperty("rankRequired").intValue = 2;   // rank 2 (the author 2026-11-08)
        so.FindProperty("aircraftGLimit").floatValue = 2.5f;
        so.FindProperty("PIDReferenceAirspeed").floatValue = 200f;
        so.FindProperty("maxSpeed").floatValue = 240f;
        so.FindProperty("takeoffSpeed").floatValue = 78f;
        so.FindProperty("takeoffDistance").floatValue = 1500f;
        so.FindProperty("verticalLanding").boolValue = false;
        so.FindProperty("turningRadius").floatValue = 3000f;
        so.FindProperty("cornerSpeed").floatValue = 175f;
        so.FindProperty("approachSpeed").floatValue = 88f;
        so.FindProperty("landingSpeed").floatValue = 82f;
        so.FindProperty("shortLandingSpeed").floatValue = 77f;
        so.FindProperty("groundTurningRadius").floatValue = 25f;
        so.FindProperty("DefaultFuelLevel").floatValue = 0.5f;
        so.FindProperty("cruiseThrottle").floatValue = 0.8f;
        // the Medusa HUD's nozzle and hover apps expect its STOVL systems; the Darkreach set is the plain subsonic jet one
        so.FindProperty("HUDExtras").objectReferenceValue = HudExtras();
        // own damage diagram (the author 2026-11-01): P220 planform, one full-frame sprite per airframe part, like the PB-22
        var sdp = StatusDisplayP220();
        if (sdp != null) so.FindProperty("StatusDisplay").objectReferenceValue = sdp;
        // house livery (0.3.27): Primeva Link olive and white, painted into the one skin texture like the stock liveries
        // 0.4.13 (the author 2026-11-08): + Primeva Link line service (any faction) and the PALA air force grey, locked to PALA
        // like the stock faction liveries (the faction placeholder is swapped for the game's Faction by the mod builder)
        string[,] LIVS = { { "P-LINK Demonstrator", "P220_livery_plink", "" }, { "Primeva Link Service", "P220_livery_civil", "" },
                           { "PALA Air Force Grey", "P220_livery_pala", "Primeva" },
                           { "Primevan Royal Family", "P220_livery_royal", "Primeva" } };   // bonus livery: gloss black, crimson swoosh, gold trim
        var liv = so.FindProperty("liveries"); liv.arraySize = LIVS.GetLength(0);
        for (int i = 0; i < LIVS.GetLength(0); i++)
        {
            var li = liv.GetArrayElementAtIndex(i);
            li.FindPropertyRelative("name").stringValue = LIVS[i, 0];
            Object fac = null;
            if (LIVS[i, 2] != "")
            {
                fac = AssetDatabase.LoadMainAssetAtPath("Assets/Blueprinter/_donotship/MonoBehaviour/" + LIVS[i, 2] + "_PLACEHOLDER.asset");
                if (fac == null) log.AppendLine("MISSING FACTION " + LIVS[i, 2]);
            }
            li.FindPropertyRelative("faction").objectReferenceValue = fac;
            string guid = AssetDatabase.AssetPathToGUID(ART + LIVS[i, 1] + ".asset");
            if (string.IsNullOrEmpty(guid)) log.AppendLine("MISSING LIVERY " + LIVS[i, 1]);
            li.FindPropertyRelative("assetReference.m_AssetGUID").stringValue = guid;
            li.FindPropertyRelative("assetReference.m_SubObjectName").stringValue = "";
        }
        var lo = so.FindProperty("loadouts");
        for (int i = 0; i < lo.arraySize; i++)
        {
            var w = lo.GetArrayElementAtIndex(i).FindPropertyRelative("weapons"); w.arraySize = 6;
            for (int k = 0; k < 6; k++) w.GetArrayElementAtIndex(k).objectReferenceValue = null;
            // default loadout (0.3.29): radar, MMR-S3 x2 on the wings, AGM-99 x2 left and PAB-80LR x4 right in the bay, tail laser
            w.GetArrayElementAtIndex(0).objectReferenceValue = Mount("P220_GlobalEye");
            w.GetArrayElementAtIndex(1).objectReferenceValue = Mount("AAM1_double");
            w.GetArrayElementAtIndex(2).objectReferenceValue = Mount("AShM2_internalx2_stack");
            w.GetArrayElementAtIndex(3).objectReferenceValue = Mount("bomb_glide1_quad_internal");
            w.GetArrayElementAtIndex(5).objectReferenceValue = Mount("P220_laser20");
            for (int k = 1; k <= 3; k++) if (w.GetArrayElementAtIndex(k).objectReferenceValue == null) log.AppendLine("default loadout: slot " + k + " mount not found");
        }
        so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(par);

        var def = AssetDatabase.LoadMainAssetAtPath(DEF);
        so = new SerializedObject(def);
        so.FindProperty("jsonKey").stringValue = "P220Primrose";
        so.FindProperty("unitName").stringValue = "P220 Primrose";
        // game update ~2026-10-30: liveries (meta.json "Aircraft") and Workshop uploads match this tag
        var wt = so.FindProperty("WorkshopTag"); if (wt != null) wt.stringValue = "P220 Primrose"; else log.AppendLine("no WorkshopTag field (old game DLL?)");
        so.FindProperty("code").stringValue = "P220";
        so.FindProperty("description").stringValue = "A domestic-built twin-engine airliner flown by Primeva Link (P-LINK), pressed into military service. This conversion adds a suite of aircraft survivability equipment including a rear aspect defensive laser. It also carries a SpectralEye dorsal radar, a variety of wing pylon options, and internal weapons in a rear fuselage bay.";
        // own map and aircraft selection icon (white top-view silhouette, nose up, like the stock icons), map scale 1.3
        string ip = ART + "P220_icon.png";
        var ti = AssetImporter.GetAtPath(ip) as TextureImporter;
        if (ti != null)
        {
            ti.textureType = TextureImporterType.Sprite; ti.spriteImportMode = SpriteImportMode.Single; ti.alphaIsTransparency = true;
            ti.mipmapEnabled = false; ti.textureCompression = TextureImporterCompression.Uncompressed; ti.filterMode = FilterMode.Bilinear;
            ti.SaveAndReimport();
            so.FindProperty("mapIcon").objectReferenceValue = AssetDatabase.LoadAssetAtPath<Sprite>(ip);
        }
        else log.AppendLine("NO ICON at " + ip);
        so.FindProperty("mapIconSize").floatValue = 1.3f;
        so.FindProperty("radarSize").floatValue = 2f;   // RCS 2 (the author 2026-11-01): an airliner-sized return
        so.FindProperty("length").floatValue = 38.7f;
        so.FindProperty("width").floatValue = 35.1f;
        so.FindProperty("height").floatValue = 11.5f;
        so.FindProperty("value").floatValue = 95f;   // the author 2026-11-08: under the Medusa (145), airliner conversion; between Vortex 90 and Tarantula 118
        so.FindProperty("mass").floatValue = 44700f;
        so.FindProperty("spawnOffset").vector3Value = new Vector3(0f, 3.86f, 0f);
        so.FindProperty("unitPrefab").objectReferenceValue = pf;
        so.FindProperty("aircraftParameters").objectReferenceValue = par;
        var ai = so.FindProperty("aircraftInfo");
        if (ai != null)
        {
            so.FindProperty("aircraftInfo.emptyWeight").floatValue = 44700f;
            so.FindProperty("aircraftInfo.maxWeight").floatValue = 70900f;
            so.FindProperty("aircraftInfo.maxSpeed").floatValue = 871f;
            so.FindProperty("aircraftInfo.stallSpeed").floatValue = 235f;
            so.FindProperty("aircraftInfo.maneuverability").floatValue = 2f;
        }
        so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(def);
        // the prefab's Aircraft.definition must point at our definition
        var pc = PrefabUtility.LoadPrefabContents(DST);
        try { Set(C(pc.transform, "Aircraft"), "definition", def); PrefabUtility.SaveAsPrefabAsset(pc, DST); }
        finally { PrefabUtility.UnloadPrefabContents(pc); }

        string op = MOD + "OpAddAircraftToHangars.asset";
        if (AssetDatabase.LoadMainAssetAtPath(op) == null)
        {
            var o = ScriptableObject.CreateInstance("OpAddAircraftToHangars");
            if (o == null) { log.AppendLine("no OpAddAircraftToHangars type"); return; }
            AssetDatabase.CreateAsset(o, op);
        }
        so = new SerializedObject(AssetDatabase.LoadMainAssetAtPath(op));
        so.FindProperty("aircraftJsonKey").stringValue = "P220Primrose";
        var hs = so.FindProperty("hangars"); hs.arraySize = 1;
        hs.GetArrayElementAtIndex(0).FindPropertyRelative("hangarUnitJsonKey").stringValue = "hangar_med";
        var hn = hs.GetArrayElementAtIndex(0).FindPropertyRelative("hangarNames"); hn.arraySize = 1; hn.GetArrayElementAtIndex(0).stringValue = "hangar_med";
        so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(so.targetObject);
        log.AppendLine("def, parameters, hangar op written");
    }
}
