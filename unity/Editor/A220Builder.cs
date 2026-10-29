using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

// Builds A220Airliner.prefab from a pristine copy of the EW-25 Medusa plus the A220 art (A220_parts.fbx + A220_layout.json),
// and the mod's own def, parameters, hangar op and weapon mounts. Run from the menu (A220 > Rebuild) or A220Builder.Build().
// Every value is a literal on purpose.
public static class A220Builder
{
    const string MOD = "Assets/Blueprinter/Mods/A220Airliner/";
    const string ART = MOD + "Art/";
    const string MNT = MOD + "Mounts/";
    const string TOOLS = "Assets/A220Tools/";
    const string SRC = TOOLS + "A220_ew1src.prefab";
    const string DST = MOD + "A220Airliner.prefab";
    const string DEF = MOD + "A220Airliner_def.asset";
    const string PAR = MOD + "A220Airliner_Parameters.asset";
    const string PH = "Assets/Blueprinter/_donotship/";
    const string EW1 = PH + "GameObject/EW1_PLACEHOLDER.prefab";

    [System.Serializable] class E { public string name, coll, kind; public float[] pos, rot, bmin, bmax; public string[] mats; }
    [System.Serializable] class W { public E[] items; }

    static Dictionary<string, E> L;
    static Dictionary<string, Mesh> M;
    static Dictionary<string, Material> MAT;
    static Transform root;
    static StringBuilder log;
    static readonly HashSet<Object> doomed = new HashSet<Object>();
    static readonly List<GameObject> doomedRoots = new List<GameObject>();
    static readonly List<Component> doomedComps = new List<Component>();

    [MenuItem("A220/Rebuild")]
    public static void Menu() { Debug.Log(Build()); }

    // ------------------------------------------------------------------ helpers
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
        if (!AssetDatabase.IsValidFolder("Assets/A220Tools")) AssetDatabase.CreateFolder("Assets", "A220Tools");
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
        var imp = (ModelImporter)AssetImporter.GetAtPath(ART + "A220_parts.fbx");
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
        L = JsonUtility.FromJson<W>("{\"items\":" + System.IO.File.ReadAllText(ART + "A220_layout.json") + "}").items.ToDictionary(e => e.name);
        M = new Dictionary<string, Mesh>();
        foreach (var o in AssetDatabase.LoadAllAssetsAtPath(ART + "A220_parts.fbx")) if (o is Mesh) M[o.name] = (Mesh)o;
        MAT = new Dictionary<string, Material>();
        MAT["A220_skin"] = LitMat("A220_skin", new Color32(222, 224, 228, 255), 0.55f, 0f);
        MAT["A220_dark"] = LitMat("A220_dark", new Color32(22, 24, 28, 255), 0.75f, 0f);
        MAT["A220_metal"] = LitMat("A220_metal", new Color32(105, 108, 112, 255), 0.35f, 0.4f);
        MAT["A220_tyre"] = LitMat("A220_tyre", new Color32(16, 16, 16, 255), 0.15f, 0f);
        MAT["A220_window"] = LitMat("A220_window", new Color32(18, 21, 26, 255), 0.85f, 0f);
        MAT["A220_bay"] = LitMat("A220_bay", new Color32(78, 80, 83, 255), 0.3f, 0.2f);
        // the Medusa canopy glass (mostly clear); the parts' glass UVs sit in the clear middle of its texture
        var glass = AssetDatabase.LoadAssetAtPath<Material>(PH + "Material/EW1_glass_PLACEHOLDER.mat");
        MAT["A220_glass"] = glass != null ? glass : MAT["A220_dark"];
        if (glass == null) log.AppendLine("EW1_glass_PLACEHOLDER not found, windshield is dark paint");
        try { Mounts(); } catch (System.Exception ex) { log.AppendLine("MOUNTS ERROR " + ex); }

        root = PrefabUtility.LoadPrefabContents(SRC).transform;
        try
        {
            Body();
            Wings();
            MovingPanels();
            Engines();
            Tail();
            MainGear("L", -1f); MainGear("R", 1f);
            NoseGear();
            Misc();
            Purge();
            Weapons();
            AeroAndDamage();
            root.name = "A220Airliner";
            PrefabUtility.SaveAsPrefabAsset(root.gameObject, DST);
            log.AppendLine("saved " + DST);
        }
        catch (System.Exception ex) { log.AppendLine("ERROR " + ex); }
        finally { PrefabUtility.UnloadPrefabContents(root.gameObject); }
        try { Assets(); } catch (System.Exception ex) { log.AppendLine("ASSETS ERROR " + ex); }
        AssetDatabase.SaveAssets();
        return log.ToString();
    }

    // ------------------------------------------------------------------ fuselage, cockpit, crew
    static void Body()
    {
        SetMesh(root, "fuselage"); SetCol(root, "fuselage_colmesh");
        var rl = root.Find("fuselage_lod1"); if (rl != null) rl.GetComponent<MeshFilter>().sharedMesh = M["fuselage_colmesh"];
        PartAt("fuselage_F"); PartAt("cockpit_R"); PartAt("cockpit_F"); PartAt("nose");
        // the Medusa crew stations ride cockpit_F, whose pivot puts them on the A220 flight deck; its bubble canopy is
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
        foreach (var n in new[] { "RearSeater1", "RearSeater2" }) { var t = Need(n); t.position = P(n); t.rotation = Quaternion.identity; }
        foreach (var n in new[] { "targetCamForward", "targetCamRear", "landingCamPoint" }) Need(n).position = P(n);
        var fR = PartAt("fuselage_R");
        foreach (var s in new[] { "L", "R" })
        {
            var fe = Need("flareEjector_" + s); fe.SetParent(fR, true); fe.position = P("flareEjector_" + s);
        }
        DoomName("fuselage_RL"); DoomName("fuselage_RR");
        PartAt("tail");
        var ck = Need("cockpit_F_int");
        var b = ck.GetComponent<Renderer>().bounds;
        log.AppendLine("Medusa cockpit interior bounds " + b.min.ToString("F2") + " .. " + b.max.ToString("F2"));
        log.AppendLine("helmet (pilot) at " + Find(Need("pilot"), "helmetCamPoint").position.ToString("F2"));
    }

    // ------------------------------------------------------------------ forward doors (the Medusa crew door Canopies)
    static void ForwardDoors()
    {
        foreach (var s in new[] { "L", "R" })
        {
            var door = Need("door_" + s); var hinge = door.parent; var mount = hinge.parent;
            var hp = P("fdoor_" + s + "_hinge");
            // CanopyHinge turns its transform about local X: point local X straight up for a vertical hinge line
            mount.position = hp; mount.rotation = Quaternion.FromToRotation(Vector3.right, Vector3.up);
            hinge.localPosition = Vector3.zero; hinge.localRotation = Quaternion.identity;
            door.position = P("fdoor_" + s); door.rotation = Quaternion.identity; door.localScale = Vector3.one;
            SetMesh(door, "fdoor_" + s);
            var mc = door.GetComponent<MeshCollider>();
            if (mc != null) { mc.convex = true; mc.sharedMesh = M["fdoor_" + s + "_colmesh"]; }
            foreach (Transform ch in door) NoMesh(ch);
            float x0 = Mathf.Abs(door.GetComponent<Renderer>().bounds.center.x);
            hinge.localEulerAngles = Vector3.right * 80f; float xa = Mathf.Abs(door.GetComponent<Renderer>().bounds.center.x);
            hinge.localEulerAngles = Vector3.right * -80f; float xb = Mathf.Abs(door.GetComponent<Renderer>().bounds.center.x);
            hinge.localRotation = Quaternion.identity;
            float open = xa > xb ? 80f : -80f;
            var cso = new SerializedObject(C(door, "Canopy"));
            var hs = cso.FindProperty("canopyHinges"); hs.arraySize = 1;
            hs.GetArrayElementAtIndex(0).FindPropertyRelative("transform").objectReferenceValue = hinge;
            hs.GetArrayElementAtIndex(0).FindPropertyRelative("hingeAngle").floatValue = open;
            cso.FindProperty("forcePosition").vector3Value = new Vector3(s == "L" ? -1f : 1f, 0f, 0f);
            cso.ApplyModifiedPropertiesWithoutUndo();
            log.AppendLine("forward door " + s + " opens " + open + " (closed |x| " + x0.ToString("F2") + ")");
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
        t.position = mid; t.rotation = Quaternion.identity;
        NoMesh(t); SetCol(t, mesh + "_colmesh");
        var h = Find(root, hingeName);
        if (h == null) h = New(hingeName, t);
        if (h.parent != t) h.SetParent(t, true);
        var dir = (b - a).normalized; if (Vector3.Dot(dir, Vector3.right) < 0f && Mathf.Abs(dir.x) > 0.5f) dir = -dir;
        h.position = mid; h.rotation = Quaternion.FromToRotation(Vector3.right, dir);
        var v = Find(h, visName);
        if (v == null) v = New(visName, h);
        v.position = mid; v.rotation = Quaternion.identity;
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
            var nl = Need("navlight_" + s); nl.position = P("navlight_" + s);
            var nle = Need("navlight_" + s + "_effects"); nle.position = P("navlight_" + s) + new Vector3(s == "L" ? -0.05f : 0.05f, 0f, 0f);
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
        // the Medusa radar jammer (ECM) and flare dispenser stay with their Medusa values for now; capacitor cut to 600 kJ
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
        float fold = FoldSign(hinge, ax, new Vector3(-sg, 0.3f, 0f), 90f);
        log.AppendLine("main gear " + s + " foldDegrees " + fold);
        Set(lg, "suspensionTravel", travel); Set(lg, "wheelRadius", r);
        Set(lg, "springRate", 2500000f); Set(lg, "dampingRate", 300000f); Set(lg, "maxCompression", 0.40f);   // breaks at ~4.5x static load, like the stock gear (0.6 never broke: travel is 0.55)
        Set(lg, "contactArea", 0.05f);   // tyre footprint: sets how deep the gear sinks and drags on grass; 0.05 gives a FastBomber-like ground pressure so rough ground breaks it
        Set(lg, "mass", 600f); Set(lg, "foldDegrees", fold); Set(lg, "hingeFoldMotion", Vector3.zero); Set(lg, "foldSpeed", 25f);
        Set(lg, "extendedDrag", 4f); Set(lg, "attachedPart", C(Need("wing1b_" + s), "AeroPart"));
        Set(lg, "castPoint", cast); Set(lg, "axle", ax);
        Size(lg, "movingParts", 0); Size(lg, "gearDoors", 0);
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
        lm.rotation = Quaternion.Euler(0f, 180f, 0f);      // the laser looks aft; 135 deg either side covers a 270 deg rear arc
    }

    // ------------------------------------------------------------------ hardpoints
    static readonly string[] WingOptions = { "AAM1_single", "AAM1_double", "AAM1_triple", "AAM2_single", "AAM2_double", "AAM2_triple",
        "AAM4_single", "AAM4_double", "AGM_heavy_single", "AGM_heavy_double", "ARM1_single", "ARM2_single", "AShM2_single",
        "AShM2_double", "AShM3_single", "AIR-2_Genie_single", "Rocket2_4Pod", "SpecialSmokePod", "ECMPod1" };
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
        while (sets.arraySize > 5) sets.DeleteArrayElementAtIndex(sets.arraySize - 1);
        var wing = new List<Object> { null };
        foreach (var n in WingOptions) { try { wing.Add(Mount(n)); } catch (System.Exception ex) { log.AppendLine("wing option skipped: " + ex.Message); } }
        // weapon cycling follows set order: the tail laser goes last
        HardpointSet(sets.GetArrayElementAtIndex(0), "Dorsal Radar", new Object[] { null, Mount("A220_GlobalEye") }, Need("dorsalMount"), C(root, "AeroPart"));
        HardpointSet(sets.GetArrayElementAtIndex(1), "Wing Pylons", wing.ToArray(), Need("pylon_L1"), AP("wing2_L"), Need("pylon_R1"), AP("wing2_R"));
        HardpointSet(sets.GetArrayElementAtIndex(2), "Bay Left", bayOpts.ToArray(), Need("weaponBayHardpoint"), AP("fuselage_R"));
        HardpointSet(sets.GetArrayElementAtIndex(3), "Bay Right", bayOpts.ToArray(), Need("weaponBayHardpoint_R"), AP("fuselage_R"));
        HardpointSet(sets.GetArrayElementAtIndex(4), "Tail Laser", new Object[] { null, Mount("A220_laser20") }, Need("laserMount"), AP("tail"));
        for (int si = 0; si < 5; si++)
        {
            var hps = sets.GetArrayElementAtIndex(si).FindPropertyRelative("hardpoints");
            for (int i = 0; i < hps.arraySize; i++)
            {
                var bd = hps.GetArrayElementAtIndex(i).FindPropertyRelative("bayDoors");
                bool bay = si == 2 || si == 3;
                bd.arraySize = bay ? doors.Count : 0;
                for (int k = 0; bay && k < doors.Count; k++) bd.GetArrayElementAtIndex(k).objectReferenceValue = doors[k];
            }
        }
        so.ApplyModifiedPropertiesWithoutUndo();
        log.AppendLine("hardpoints: laser, dorsal radar, wing pylons (" + (wing.Count - 1) + " options), bay left/right (" + (bayOpts.Count - 1) + " options, " + doors.Count + " doors)");
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
        Part("", 8000f, 0f, 0.55f, 5000f);
        Part("fuselage_F", 5000f, 0f, 0.15f, 0f);
        Part("cockpit_R", 5000f, 0f, 0.2f, -1f);
        Part("cockpit_F", 1800f, 0f, 0.15f, -1f);
        Part("nose", 300f, 0f, 0.1f, -1f);
        Part("fuselage_R", 5500f, 0f, 0.2f, 0f);
        Part("tail", 1500f, 0f, 0.15f, -1f);
        Part("vstab_L", 500f, 10f, 0.03f, -1f); Part("vstab_R", 300f, 6f, 0.02f, -1f);
        Part("rudder_L", 120f, 3.6f, 0f, -1f); Part("rudder_R", 100f, 3f, 0f, -1f);
        foreach (var s in new[] { "L", "R" })
        {
            Part("wing1a_" + s, 900f, 14.5f, 0.05f, 700f);
            Part("wing1b_" + s, 2000f, 35f, 0.12f, 1800f);
            Part("wing2_" + s, 1100f, 22f, 0.08f, 900f);
            Part("wing3_" + s, 600f, 13f, 0.05f, 200f);
            Part("wingtip_" + s, 120f, 3.5f, 0.02f, -1f);
            Part("flap_" + s, 250f, 13f, 0.02f, -1f);
            Part("aileron_" + s, 120f, 6.5f, 0f, -1f);
            Part("intake_" + s, 300f, 0f, 0.03f, -1f);
            Part("engine_" + s, 2300f, 0f, 0.25f, -1f);
            Part("hstab_" + s, 450f, 12f, 0.04f, -1f);
            Part("elevator_" + s, 150f, 6.5f, 0f, -1f);
            foreach (var w in new[] { "wing1a_", "wing1b_", "wing2_", "wing3_", "wingtip_", "hstab_", "aileron_", "elevator_" })
                Set(AP(w + s), "centerOfLift", Vector3.zero);
            // flap and aileron lift acts at the wing's quarter chord, not on the hinge line behind the CG
            var fq = (P("wing1b_" + s) + P("wing2_" + s)) * 0.5f;
            Set(AP("flap_" + s), "centerOfLift", fq - Need("flap_" + s).position);
            Set(AP("aileron_" + s), "centerOfLift", P("wing3_" + s) - Need("aileron_" + s).position);
            var tj = C(Need("engine_" + s), "Turbojet");
            Set(tj, "maxThrust", 125000f); Set(tj, "maxSpeed", 300f);
            Set(tj, "fuelConsumptionMin", 0.2f); Set(tj, "fuelConsumptionMax", 1.4f);
            Set(tj, "failureMessage", s == "L" ? "LEFT ENGINE FIRE" : "RIGHT ENGINE FIRE");
            Set(C(Need("nozzle_R" + s), "JetNozzle"), "IRMax", 4f);
            var el = C(Need("elevator_" + s), "ControlSurface"); Set(el, "pitchRange", -25f); Set(el, "servoSpeed", 40f);
            var ai = C(Need("aileron_" + s), "ControlSurface"); Set(ai, "rollRange", s == "L" ? -26f : 26f); Set(ai, "servoSpeed", 50f);
        }
        foreach (var s in new[] { "L", "R" }) { var ru = C(Need("rudder_" + s), "ControlSurface"); Set(ru, "yawRange", -28f); Set(ru, "servoSpeed", 35f); }
        root.GetComponent<Rigidbody>().mass = 44700f;

        // joints: every part to its structural neighbours (jointed hulls may overlap; unjointed ones must not)
        // every fuselage section is held by its neighbour and by the section beyond it, so the long body stays stiff
        // instead of flexing at each single joint (the PB-22 layout)
        Joints("nose", "cockpit_F", 150000f, "cockpit_R", 100000f);
        Joints("cockpit_F", "cockpit_R", 600000f, "fuselage_F", 400000f);
        Joints("cockpit_R", "fuselage_F", 800000f, root.name, 500000f);
        Joints("fuselage_F", root.name, 1000000f, "fuselage_R", 500000f);
        Joints("fuselage_R", root.name, 1000000f);
        Joints("tail", "fuselage_R", 600000f, root.name, 300000f);
        Joints("vstab_L", "tail", 400000f, "fuselage_R", 200000f);
        Joints("vstab_R", "vstab_L", 250000f);
        Joints("rudder_L", "vstab_L", 120000f, "tail", 60000f);
        Joints("rudder_R", "vstab_R", 100000f, "rudder_L", 40000f);
        foreach (var s in new[] { "L", "R" })
        {
            Joints("hstab_" + s, "tail", 300000f);
            Joints("elevator_" + s, "hstab_" + s, 150000f, "tail", 60000f);
            // wing joints solve at 12 iterations like the PB-22's outer wing (less flex under load), and every outer
            // panel is also held by the panel beyond its neighbour, like the fuselage, so the span bends as one piece
            jointIterations = 12;
            Joints("wing1a_" + s, root.name, 1800000f);
            Joints("wing1b_" + s, "wing1a_" + s, 1400000f, root.name, 1000000f);
            Joints("wing2_" + s, "wing1b_" + s, 1200000f, "wing1a_" + s, 600000f);
            Joints("wing3_" + s, "wing2_" + s, 900000f, "wing1b_" + s, 400000f);
            Joints("wingtip_" + s, "wing3_" + s, 300000f, "wing2_" + s, 120000f);
            Joints("flap_" + s, "wing2_" + s, 1000000f, "wing1b_" + s, 1000000f, "wing1a_" + s, 500000f, root.name, 250000f);
            Joints("aileron_" + s, "wing3_" + s, 500000f, "wing2_" + s, 200000f);
            jointIterations = 6;
            Joints("intake_" + s, "wing1b_" + s, 600000f);
            Joints("engine_" + s, "intake_" + s, 500000f, "wing1b_" + s, 300000f);
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
    static void Mounts()
    {
        // laser: the Spearhead's own defensive laser turret. onlyDefensive means it only engages missiles aimed at this
        // aircraft; it is cued by the aircraft's sensors (parentUnitTargetDetector) and traverses 135 deg either side of
        // the tail for a 270 deg rear arc. The Medusa laser it replaces had no turret, so nothing ever told it to fire.
        var mbt = CopyPrefab("MBT1", "mbt_tmp");
        var go = new GameObject("A220_laser20");
        try
        {
            var lt = mbt.GetComponentsInChildren<Transform>(true).First(t => t.name == "laser_turret");
            lt.SetParent(go.transform, false); lt.localPosition = Vector3.zero; lt.localRotation = Quaternion.identity;
            var tur = C(lt, "Turret");
            Set(tur, "attachedUnit", null); Set(tur, "targetAcquisitionMode", 0);
            Size(tur, "targetDetectors", 0); Size(tur, "criticalParts", 0);
            Set(tur, "traverseRange", 135f); Set(tur, "traverseRate", 360f);   // it rests wherever the last target was; swing back fast
            Set(tur, "minElevation", -60f); Set(tur, "maxElevation", 60f); Set(tur, "elevationRate", 120f);
            Object.DestroyImmediate(C(lt, "TargetDetector"));
            Object.DestroyImmediate(lt.GetComponent<SphereCollider>());
            Object.DestroyImmediate(C(lt, "UnitPart"));
            var lz = C(lt.Find("laser_barrel"), "Laser");
            Set(lz, "attachedUnit", null);
            Set(lz, "vehicularPowerSupply", false);
            // Medusa laser output: 120 kW, 40 fire damage, falling off to nothing at 15 km
            Set(lz, "power", 120f); Set(lz, "fireDamage", 40f); Set(lz, "trackingRate", 120f);
            Set(lz, "damageAtRange", new AnimationCurve(new Keyframe(0f, 1f), new Keyframe(15000f, 0f)));   // draw from the aircraft's capacitor like the Medusa laser
            var info = AssetDatabase.LoadMainAssetAtPath(Placeholder("Laser_APS1", "WeaponInfo"));
            var m = SaveMount(go, "A220_laser20", "laser_EW1", info, "120kW Defence Laser");
            Set(m, "turret", true);
            log.AppendLine("laser turret: " + string.Join(", ", go.GetComponentsInChildren<Component>(true).Select(c => c.GetType().Name)));
        }
        finally { Object.DestroyImmediate(go); Object.DestroyImmediate(mbt); }
        // GlobalEye: the Medusa radome mount (radar values kept) with a fixed Erieye beam instead of the rotodome
        go = CopyPrefab("Radome1", "A220_GlobalEye");
        try
        {
            var rd = go.transform.Find("Radome");
            rd.localPosition = Vector3.zero; rd.localRotation = Quaternion.identity;
            var mf = rd.GetComponent<MeshFilter>(); mf.sharedMesh = M["globaleye"];
            rd.GetComponent<MeshRenderer>().sharedMaterials = new[] { MAT["A220_skin"] };
            var mc = rd.GetComponent<MeshCollider>(); if (mc != null) { mc.convex = true; mc.sharedMesh = M["globaleye_colmesh"]; }
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
            SaveMount(go, "A220_GlobalEye", "Radome1", null, "GlobalEye AEW Radar");
        }
        finally { Object.DestroyImmediate(go); }
    }

    // ------------------------------------------------------------------ definition, parameters, hangar op
    static void Assets()
    {
        var pf = AssetDatabase.LoadAssetAtPath<GameObject>(DST);
        var par = AssetDatabase.LoadMainAssetAtPath(PAR);
        var so = new SerializedObject(par);
        so.FindProperty("aircraftName").stringValue = "P220 Primrose";
        so.FindProperty("rankRequired").intValue = 0;
        so.FindProperty("aircraftGLimit").floatValue = 2.5f;
        so.FindProperty("PIDReferenceAirspeed").floatValue = 200f;
        so.FindProperty("maxSpeed").floatValue = 240f;
        so.FindProperty("takeoffSpeed").floatValue = 75f;
        so.FindProperty("takeoffDistance").floatValue = 1500f;
        so.FindProperty("verticalLanding").boolValue = false;
        so.FindProperty("turningRadius").floatValue = 3000f;
        so.FindProperty("cornerSpeed").floatValue = 160f;
        so.FindProperty("approachSpeed").floatValue = 80f;
        so.FindProperty("landingSpeed").floatValue = 75f;
        so.FindProperty("shortLandingSpeed").floatValue = 70f;
        so.FindProperty("groundTurningRadius").floatValue = 25f;
        so.FindProperty("DefaultFuelLevel").floatValue = 0.5f;
        so.FindProperty("cruiseThrottle").floatValue = 0.8f;
        // the Medusa HUD's nozzle and hover apps expect its STOVL systems; the Darkreach set is the plain subsonic jet one
        so.FindProperty("HUDExtras").objectReferenceValue = AssetDatabase.LoadAssetAtPath<GameObject>(PH + "GameObject/SFB_HUDExtras_PLACEHOLDER.prefab");
        // one blank livery: the hangar preview and Fly button need liveries[0]; the Medusa liveries do not fit this airframe
        var liv = so.FindProperty("liveries"); liv.arraySize = 1;
        var li = liv.GetArrayElementAtIndex(0);
        li.FindPropertyRelative("name").stringValue = "Default";
        li.FindPropertyRelative("faction").objectReferenceValue = null;
        li.FindPropertyRelative("assetReference.m_AssetGUID").stringValue = "";
        li.FindPropertyRelative("assetReference.m_SubObjectName").stringValue = "";
        // three hardpoint sets: tail laser, dorsal radar, wing pylons
        var lo = so.FindProperty("loadouts");
        for (int i = 0; i < lo.arraySize; i++)
        {
            var w = lo.GetArrayElementAtIndex(i).FindPropertyRelative("weapons"); w.arraySize = 5;
            for (int k = 0; k < 5; k++) w.GetArrayElementAtIndex(k).objectReferenceValue = null;
            w.GetArrayElementAtIndex(0).objectReferenceValue = Mount("A220_GlobalEye");
            w.GetArrayElementAtIndex(4).objectReferenceValue = Mount("A220_laser20");
        }
        so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(par);

        var def = AssetDatabase.LoadMainAssetAtPath(DEF);
        so = new SerializedObject(def);
        so.FindProperty("jsonKey").stringValue = "A220Airliner";
        so.FindProperty("unitName").stringValue = "P220 Primrose";
        so.FindProperty("code").stringValue = "P220";
        so.FindProperty("description").stringValue = "A domestically built twin-engine airliner flown by Primeva Link (PLINK), pressed into military service in medical transport, radar and light cargo roles. This conversion carries a GlobalEye dorsal radar, a tail-mounted 20 kW defensive pulse laser that engages missiles aimed at the aircraft, an internal weapons bay and light wing pylons.";
        so.FindProperty("length").floatValue = 38.7f;
        so.FindProperty("width").floatValue = 35.1f;
        so.FindProperty("height").floatValue = 11.5f;
        so.FindProperty("value").floatValue = 0f;
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
            so.FindProperty("aircraftInfo.stallSpeed").floatValue = 210f;
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
        so.FindProperty("aircraftJsonKey").stringValue = "A220Airliner";
        var hs = so.FindProperty("hangars"); hs.arraySize = 1;
        hs.GetArrayElementAtIndex(0).FindPropertyRelative("hangarUnitJsonKey").stringValue = "hangar_med";
        var hn = hs.GetArrayElementAtIndex(0).FindPropertyRelative("hangarNames"); hn.arraySize = 1; hn.GetArrayElementAtIndex(0).stringValue = "hangar_med";
        so.ApplyModifiedPropertiesWithoutUndo(); EditorUtility.SetDirty(so.targetObject);
        log.AppendLine("def, parameters, hangar op written");
    }
}
