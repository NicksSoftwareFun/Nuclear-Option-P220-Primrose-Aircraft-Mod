using System;
using System.Collections.Generic;
using System.Reflection;
using BepInEx;
using HarmonyLib;
using UnityEngine;

namespace P220Primrose
{
    // Carries the P220 Primrose bundle (embedded .nobp, loaded by Blueprinter) and fits the airliner through the medium hangar
    // door: only the fin is taller than the 8 m door (the hangar is 80 m wide and 48.7 m deep), so the aircraft spawns
    // with the upper half of its fin folded 90 degrees to starboard about a hinge level with the top of the dorsal radar,
    // and the fin folds up vertical once the aircraft has rolled 25 m from its spawn point. Only aircraft that come out
    // of a hangar are folded; runway and air spawns, the hangar preview and the encyclopedia show it upright. No stock
    // aircraft folds its fin, so this needs the plugin.
    [BepInPlugin("nick.nuclearoption.p220primrose", "P220 Primrose", "1.0.1")]
    [BepInDependency("com.nikkorap.blueprinter", BepInDependency.DependencyFlags.SoftDependency)]
    public class Plugin : BaseUnityPlugin
    {
        internal static BepInEx.Logging.ManualLogSource Log;

        private void Awake()
        {
            Log = Logger;
            try
            {
                var awake = R.T("Aircraft")?.GetMethod("Awake", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
                if (awake == null) { Logger.LogWarning("P220: Aircraft.Awake not found, hangar scaling off"); return; }
                var h = new Harmony("nick.nuclearoption.p220primrose");
                h.Patch(awake, postfix: new HarmonyMethod(typeof(Plugin), nameof(PostAwake)));
                var complex = R.T("Aircraft").GetMethod("SetComplexPhysics", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (complex != null) h.Patch(complex, prefix: new HarmonyMethod(typeof(Plugin), nameof(PreComplex)));
                var localSim = R.T("Aircraft").GetMethod("SetLocalSim", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                var modMass = R.T("UnitPart").GetMethod("ModifyMass", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (modMass != null) h.Patch(modMass, postfix: new HarmonyMethod(typeof(Plugin), nameof(PostModifyMass)));
                var aero = R.T("AeroPart");
                foreach (var name in new[] { "CreateRB", "CreateJoints" })
                {
                    var m = aero?.GetMethod(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (m != null) h.Patch(m, prefix: new HarmonyMethod(typeof(Plugin), nameof(PreSplitPart)));
                }
                if (localSim != null) h.Patch(localSim, prefix: new HarmonyMethod(typeof(Plugin), nameof(PreLocalSim)), postfix: new HarmonyMethod(typeof(Plugin), nameof(PostLocalSim)));
                LaserLog.Patch(h);
                Reversers.Patch(h);
                Thorn.Patch(h);
                Interior.Patch(h);
                var go = new GameObject("P220Runtime"); DontDestroyOnLoad(go); go.hideFlags = HideFlags.HideAndDontSave;
                go.AddComponent<P220Panel>();
                Logger.LogInfo("P220 Primrose loaded");
            }
            catch (Exception e) { Logger.LogWarning("P220: hangar scaling not applied: " + e.Message); }
        }

        private static void PostAwake(Component __instance)
        {
            try
            {
                if (!__instance.name.StartsWith("P220Primrose") || __instance.GetComponent<P220Grow>() != null) return;
                var g = __instance.gameObject.AddComponent<P220Grow>(); g.ac = __instance;
                // fold the fin before the first frame is drawn; Spawned() unfolds it again if the aircraft did not come
                // out of a hangar
                g.Prepare();
                __instance.gameObject.AddComponent<GearLight>().ac = __instance;
                __instance.gameObject.AddComponent<P220Fans>().Setup(__instance);
            }
            catch (Exception e) { Log.LogWarning("P220: scaling setup failed: " + e.Message); }
        }

        // SetLocalSim runs once as a spawned aircraft starts up, before its parts are split out. Decide here whether it
        // came out of a hangar and needs squashing.
        private static void PreLocalSim(Component __instance)
        {
            try { __instance.GetComponent<P220Grow>()?.Spawned(); }
            catch (Exception e) { Log.LogWarning("P220: hangar squash not applied: " + e.Message); }
        }

        private static void PostLocalSim(Component __instance)
        {
            try { __instance.GetComponent<P220Grow>()?.Merge(); }
            catch (Exception e) { Log.LogWarning("P220: hangar squash not applied: " + e.Message); }
        }

        // Burning fuel calls ModifyMass on the tank's part, which sets that part's rigidbody mass to the part's own mass.
        // While the airframe is one merged body that rigidbody is the whole aircraft, so a 45 t airliner suddenly weighs
        // a few tonnes on springs sized for 45 t and pogoes itself apart. Put the whole-aircraft mass back.
        private static void PostModifyMass(Component __instance)
        {
            try
            {
                var body = R.Get(__instance, "rb") as Rigidbody;
                if (body == null) return;
                var g = body.GetComponent<P220Grow>();
                if (g != null && g.Growing) g.SetMass();
            }
            catch (Exception e) { Log.LogWarning("P220: mass fix failed: " + e.Message); }
        }

        // A hardpoint mount with its own airframe part (the dorsal radar) is split out onto its own jointed rigidbody when
        // it is fitted. While the aircraft is merged and growing, keep it merged too so it grows with the fuselage; it is
        // split out at full height with the rest.
        private static bool PreSplitPart(Component __instance)
        {
            var unit = R.Get(__instance, "parentUnit") as Component;
            var g = unit != null ? unit.GetComponent<P220Grow>() : null;
            if (g == null || !g.Growing) return true;
            g.Hold(__instance);
            return false;
        }

        // the game's physics LOD must not split the airframe back into jointed parts while it is growing
        private static bool PreComplex(Component __instance)
        {
            var g = __instance.GetComponent<P220Grow>();
            if (g == null) return true;
            // the aircraft selection preview is set un-networked and then switched to jointed parts straight away: the
            // fin has to stand up before that, or the joints lock it folded
            if (!g.Growing && R.Get(__instance, "networked") is bool n && !n) { g.Preview(); return true; }
            return !g.Growing;
        }
    }

    public class P220Grow : MonoBehaviour
    {
        private const float FoldAngle = 90f;       // upper fin folded flat to starboard: the fin top drops under the 8 m door
        private const float GrowDistance = 40f;    // metres rolled from the spawn point before the fin folds up
        private const float GrowTime = 6f;         // seconds to fold up

        private class Gear { public Component c; public float radius, travel; public Transform cast; }

        internal Component ac;
        private Rigidbody rb;
        private float growStart = -1f;
        private Vector3 spawn;
        private bool decided;
        private readonly List<Gear> gears = new List<Gear>();
        private readonly List<Component> held = new List<Component>();
        private Transform fin;                     // vstab_R: the upper fin, carrying its rudder half
        // all in the aircraft root's space: the game splits the parts out of their hierarchy when the aircraft starts,
        // so the lower fin is no longer the upper fin's parent by the time it folds
        private Vector3 finPos, hinge, axis;
        private Quaternion finRot;
        private static FieldInfo fRadius, fTravel, fPatch, fCast, fBump;

        public bool Growing { get; private set; }

        private bool prepared;

        // Called as the aircraft is created, before anything is drawn: the upper fin starts folded.
        public void Prepare()
        {
            fin = FindChild(transform, "vstab_R");
            if (fin == null) return;
            var root = ac != null ? ac.transform : transform;
            // hinge line runs fore and aft along the starboard skin at the fin split (the upper fin's root). Taken from the
            // mesh vertices, not renderer bounds: in Awake the bounds can still be empty, which put the hinge at the origin
            // and left the folded fin floating above the tail (0.3.12)
            var mf = fin.GetComponent<MeshFilter>();
            if (mf == null || mf.sharedMesh == null) mf = fin.GetComponentInChildren<MeshFilter>();
            if (mf != null && mf.sharedMesh != null && mf.sharedMesh.isReadable)
            {
                var vs = mf.sharedMesh.vertices; float ymin = float.MaxValue;
                var rs = new Vector3[vs.Length];
                for (int i = 0; i < vs.Length; i++) { rs[i] = root.InverseTransformPoint(mf.transform.TransformPoint(vs[i])); ymin = Mathf.Min(ymin, rs[i].y); }
                float xmax = float.MinValue, zs = 0f; int n = 0;
                foreach (var p in rs) if (p.y < ymin + 0.15f) { xmax = Mathf.Max(xmax, p.x); zs += p.z; n++; }
                hinge = new Vector3(xmax, ymin, zs / Mathf.Max(1, n));
            }
            else
            {
                var mb = mf != null && mf.sharedMesh != null ? mf.sharedMesh.bounds : new Bounds(Vector3.zero, Vector3.one);
                var lo = root.InverseTransformPoint(fin.TransformPoint(mb.min));
                hinge = new Vector3(Mathf.Abs(root.InverseTransformPoint(fin.TransformPoint(mb.max)).x), lo.y, root.InverseTransformPoint(fin.position).z);
            }
            var fh = FindChild(transform, "finFoldHinge");      // 0.4.5: the hinge line placed by the builder, when present
            if (fh != null) hinge = root.InverseTransformPoint(fh.position);
            Plugin.Log.LogInfo("P220 fin hinge (aircraft frame) " + hinge.ToString("F2"));
            axis = root.InverseTransformDirection(fin.parent.forward);
            finPos = root.InverseTransformPoint(fin.position); finRot = Quaternion.Inverse(root.rotation) * fin.rotation;
            Fold(1f, false);
            prepared = true;
        }

        // the aircraft selection preview is a local, un-networked copy that never starts a simulation: keep its fin upright
        // (checked every frame until the aircraft starts up: the menu clears "networked" only after the aircraft is created)
        private void Update()
        {
            if (decided || !prepared) return;
            if (R.Get(ac, "networked") is bool n && !n) { decided = true; Fold(0f, false); Plugin.Log.LogInfo("P220 preview: fin upright"); Destroy(this); }
        }

        public void Preview()
        {
            if (decided) return;
            decided = true;
            if (fin != null) Fold(0f, false);
            Plugin.Log.LogInfo("P220 preview: fin upright");
            Destroy(this);
        }

        public void Spawned()
        {
            if (decided) return;
            decided = true;
            if (!prepared) Prepare();
            if (fin == null) { Destroy(this); return; }
            if (R.Get(ac, "NetworkspawningHangar") as Component == null) { Fold(0f, false); Destroy(this); return; }
            rb = GetComponent<Rigidbody>();
            var lgType = R.T("LandingGear");
            if (lgType != null)
            {
                const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                fRadius = lgType.GetField("wheelRadius", F); fTravel = lgType.GetField("suspensionTravel", F); fPatch = lgType.GetField("contactPatchSize", F);
                fCast = lgType.GetField("castPoint", F); fBump = lgType.GetField("bumpStop", F);
                foreach (var c in GetComponentsInChildren(lgType, true))
                {
                    var cast = fCast?.GetValue(c) as Transform;
                    if (cast == null) cast = (fBump?.GetValue(c) as GameObject)?.transform;
                    gears.Add(new Gear { c = c, radius = (float)fRadius.GetValue(c), travel = (float)fTravel.GetValue(c), cast = cast });
                }
            }
            Growing = true;
            Fold(1f, true);
            float gap = SettleOnFloor();
            spawn = Global();
            Plugin.Log.LogInfo("P220 upper fin folded for the hangar (wheels were " + gap.ToString("F2") + " m off the floor)");
        }

        // Measures the floor under the wheels and sets the aircraft down with its wheels just touching it, so the spawn never
        // starts with the wheels in the floor or dropping onto it. Returns how far off the floor the wheels were.
        private float SettleOnFloor()
        {
            float gap = float.MaxValue;
            foreach (var g in gears)
            {
                if (g.cast == null) continue;
                var up = transform.up;
                var bottom = g.cast.position - up * g.travel;
                foreach (var hit in Physics.RaycastAll(bottom + up * 3f, -up, 8f))
                {
                    if (hit.collider.isTrigger || (rb != null && hit.collider.attachedRigidbody == rb)) continue;
                    gap = Mathf.Min(gap, hit.distance - 3f);
                }
            }
            if (gap == float.MaxValue || Mathf.Abs(gap) > 4f) return 0f;
            var p = transform.position - transform.up * (gap - 0.02f);
            if (rb != null) { rb.position = p; rb.velocity = Vector3.zero; rb.angularVelocity = Vector3.zero; }
            transform.position = p;
            Physics.SyncTransforms();
            return gap;
        }

        // Same state the game puts a distant aircraft in: every part folded into one rigid body. The whole squashed
        // phase runs like this, so no joint is ever stretched; the parts are split out with fresh joints at full height.
        public void Merge()
        {
            if (!Growing || !Local()) return;
            R.Call(ac, "SetSimplePhysics");
            // mounts already split out (fitted before the squash) fold back in the same way the game folds its parts
            var parts = R.Get(ac, "partLookup") as System.Collections.IList;
            var aero = R.T("AeroPart");
            if (aero != null)
                foreach (var o in FindObjectsOfType(aero))
                {
                    var c = o as Component;
                    if (c == null || (parts != null && parts.Contains(c)) || R.Get(c, "parentUnit") as Component != ac) continue;
                    if (R.Get(c, "rb") as Rigidbody == rb) continue;
                    R.Call(c, "MergeWithParent");
                    Hold(c);
                }
            SetMass();
            Plugin.Log.LogInfo("P220 merged for the squashed phase: " + rb.mass.ToString("F0") + " kg, CoM z " + rb.centerOfMass.z.ToString("F2") + " m");
        }

        // While merged, the one rigidbody carries the mass of every attached part (fuel and weapons included) at the
        // parts' combined centre of mass, the same sum the game uses for the aircraft's CoM. Left alone it would take its
        // CoM from collider volumes, just behind the main wheels, and see-saw on them.
        public void SetMass()
        {
            if (rb == null) return;
            float m = 0f;
            var parts = R.Get(ac, "partLookup") as System.Collections.IEnumerable;
            if (parts != null)
                foreach (var p in parts)
                {
                    if (p == null || R.Invoke(p, "IsDetached") is bool d && d) continue;
                    if (R.Get(p, "mass") is float pm) m += pm;
                }
            if (m > 1000f) rb.mass = m;
            if (R.Invoke(ac, "CalcCenterOfMass") is Vector3 c)
                rb.centerOfMass = Quaternion.Inverse(transform.rotation) * (c - transform.position);
        }

        public void Hold(Component part)
        {
            if (!held.Contains(part)) held.Add(part);
        }

        private void FixedUpdate()
        {
            if (!Growing || ac == null) return;
            // a wreck stays the size it was destroyed at; the game handles its pieces from here as for any aircraft
            if (R.Get(ac, "disabled") is bool dead && dead) { Growing = false; Destroy(this); return; }
            if (growStart < 0f)
            {
                if ((Global() - spawn).magnitude < GrowDistance) return;
                growStart = Time.time;
            }
            float k = Mathf.Clamp01((Time.time - growStart) / GrowTime);
            Fold(1f - Mathf.SmoothStep(0f, 1f, k), Local());
            if (k < 1f) return;
            Growing = false;
            if (Local())
            {
                R.Call(ac, "SetComplexPhysics");
                foreach (var c in held)
                {
                    if (c == null || R.Get(c, "rb") as Rigidbody != rb) continue;
                    var pos = c.transform.position;
                    R.T("AeroPart").GetMethod("CreateRB").Invoke(c, new object[] { rb.GetPointVelocity(pos), pos });
                    R.Call(c, "CreateJoints");
                }
            }
            Plugin.Log.LogInfo("P220 fin folded up");
            Destroy(this);
        }

        private bool Local() => R.Get(ac, "LocalSim") is bool b && b;

        // position relative to the world origin, unaffected by the game's floating origin shifts
        private Vector3 Global()
        {
            var o = R.Static("Datum", "origin") as Transform;
            return o != null ? transform.position - o.position : transform.position;
        }

        // Folds the upper fin about its hinge: 1 = flat to starboard, 0 = upright. Every machine does this locally.
        private void Fold(float f, bool move)
        {
            var q = Quaternion.AngleAxis(-FoldAngle * f, axis);   // about the fore-aft axis, top towards starboard
            var root = ac != null ? ac.transform : transform;
            fin.SetPositionAndRotation(root.TransformPoint(hinge + q * (finPos - hinge)), root.rotation * (q * finRot));
            SyncAttach();
            if (move)
            {
                Physics.SyncTransforms();
                if (rb != null) { rb.ResetInertiaTensor(); SetMass(); }
            }
        }

        // The game records where each part sits on its parent when the part wakes up, and splits a part off as broken
        // once it is more than 0.5 m from that spot (AeroPart.CheckAttachment); merging also snaps the part back to it.
        // The fin wakes up folded, so the record is kept in step with every fold: otherwise the upright fin reads as torn
        // off the moment the parts are split out with their own joints (the 0.4.x "breaks when it reaches vertical").
        private static FieldInfo fAttach, fAPos, fARot, fAParent;
        private void SyncAttach()
        {
            if (finPart == null) { var up = R.T("UnitPart"); if (up != null) finPart = fin.GetComponent(up); }
            if (finPart == null) return;
            const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            if (fAttach == null) fAttach = R.T("UnitPart").GetField("attachInfo", F);
            var info = fAttach?.GetValue(finPart);
            if (info == null) return;
            if (fAPos == null) { var t = info.GetType(); fAPos = t.GetField("localPosition", F); fARot = t.GetField("localRotation", F); fAParent = t.GetField("parentPart", F); }
            var parent = fAParent?.GetValue(info) as Component;
            if (parent == null || fAPos == null || fARot == null) return;
            fAPos.SetValue(info, parent.transform.InverseTransformPoint(fin.position));
            fARot.SetValue(info, Quaternion.Inverse(parent.transform.rotation) * fin.rotation);
        }
        private Component finPart;

        private static Transform FindChild(Transform t, string name)
        {
            if (t.name == name) return t;
            foreach (Transform c in t) { var r = FindChild(c, name); if (r != null) return r; }
            return null;
        }
    }

    // THORN tail laser and the capacitor pack. The turret is the stock defensive laser turret; stock turrets stay where
    // they last aimed once they lose their target and their HUD hint only checks range, so this adds:
    //  - a rest pose straight aft (elevation -90 on the pod gimbal) that the ball returns to 5 s after its last target;
    //  - SHOOT / OUT OF ARC / OUT OF RANGE on the HUD when the laser is the selected weapon, using the turret's own
    //    firing cone, its elevation limit and the same airframe line check the turret makes before it fires;
    //  - the capacitor pack: an empty rear-bay mount (no weapon, so never in the weapon cycle) that adds 525 to the
    //    aircraft capacitor (75% of 600 + 100 from the built-in jammer). Stock jammers only add their capacitance when
    //    built into the airframe, so the plugin adds it when the pack is fitted and takes it away when it is removed.
    internal static class Thorn
    {
        const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        internal const float RestElevation = -90f, IdleReturn = 5f, CapPack = 525f;
        const string CapKey = "P220_capPack", ThornName = "THORN";
        static readonly Dictionary<object, Component> packs = new Dictionary<object, Component>();
        static Type turretT, coneCheckT; static FieldInfo hsHint, hsStation, hsInfo; static MethodInfo coneCheck;
        static int exclusionMask; static FieldInfo fMount;

        public static void Patch(Harmony h)
        {
            turretT = R.T("Turret");
            var att = turretT?.GetMethod("AttachToWeaponManager", F);
            if (att != null) h.Patch(att, postfix: new HarmonyMethod(typeof(Thorn), nameof(PostAttach)));
            else Plugin.Log.LogWarning("P220: Turret.AttachToWeaponManager not found, laser rest off");
            var hs = R.T("HUDTurretState"); var upd = hs?.GetMethod("UpdateWeaponDisplay", F);
            hsHint = hs?.GetField("hint", F); hsStation = hs?.GetField("weaponStation", F); hsInfo = R.T("HUDWeaponState")?.GetField("weaponInfo", F);
            coneCheckT = R.T("FiringConeChecker"); coneCheck = coneCheckT?.GetMethod("VectorWithinFiringCones", BindingFlags.Static | BindingFlags.Public);
            var pl = R.T("PhysicsLayers")?.GetField("ExclusionZonesMask", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
            object m = pl?.GetValue(null); exclusionMask = m is LayerMask lm ? lm.value : m is int i ? i : 0;
            if (upd != null && hsHint != null && hsStation != null && hsInfo != null) h.Patch(upd, postfix: new HarmonyMethod(typeof(Thorn), nameof(PostHud)));
            else Plugin.Log.LogWarning("P220: HUDTurretState fields not found, laser arc hint off");
            var err = turretT?.GetMethod("GetTurretAimError", F);
            if (err != null) h.Patch(err, postfix: new HarmonyMethod(typeof(Thorn), nameof(PostAimError)));
            else Plugin.Log.LogWarning("P220: Turret.GetTurretAimError not found, laser aiming box off");
            PatchLaser(h);
            var hp = R.T("Hardpoint"); fMount = hp?.GetField("mount", F);
            var sp = hp?.GetMethod("SpawnMount", F); var rm = hp?.GetMethod("RemoveMount", F);
            if (sp != null && rm != null && fMount != null)
            {
                h.Patch(sp, postfix: new HarmonyMethod(typeof(Thorn), nameof(PostSpawnMount)));
                h.Patch(rm, prefix: new HarmonyMethod(typeof(Thorn), nameof(PreRemoveMount)));
            }
            else Plugin.Log.LogWarning("P220: Hardpoint methods not found, capacitor pack inert");
        }

        // The beam must never touch the aircraft that carries it. Laser.FixedUpdate burns whatever its line from the
        // emitter to the target meets first, and the turret's own pre-fire check looks along the barrel, not along the
        // beam. So before each beam tick, follow the beam's real line (as Laser computes it) and hold fire while any part
        // of this aircraft is on it. The line is traced from its far end back towards the ball, so parts the beam would
        // pass out of are caught as well as parts it would run into.
        static FieldInfo lFire, lTargetT, lDir, lMaxAngle, lUnit, fParentUnit; static Type unitPartT;
        static void PatchLaser(Harmony h)
        {
            var lt = R.T("Laser"); var fu = lt?.GetMethod("FixedUpdate", F);
            lFire = lt?.GetField("fireCommanded", F); lTargetT = lt?.GetField("currentTargetTransform", F); lDir = lt?.GetField("directionTransform", F);
            lMaxAngle = lt?.GetField("maxAngle", F); lUnit = lt?.GetField("attachedUnit", F);
            unitPartT = R.T("UnitPart"); fParentUnit = unitPartT?.GetField("parentUnit", F);
            if (fu != null && lFire != null && lDir != null && lMaxAngle != null && lUnit != null && fParentUnit != null)
                h.Patch(fu, prefix: new HarmonyMethod(typeof(Thorn), nameof(PreLaserTick)));
            else Plugin.Log.LogWarning("P220: Laser fields not found, self-hit guard off");
        }
        static float lastGuardLog;
        static void PreLaserTick(Component __instance)
        {
            try
            {
                if (!(lFire.GetValue(__instance) is bool f) || !f) return;
                var unit = lUnit.GetValue(__instance) as Component;
                if (unit == null || !unit.name.StartsWith("P220Primrose")) return;
                // 0.4.2: the laser holds fire while the crew is jamming, so it never takes the capacitor charge
                // the ECM needs for a soft kill
                if (EcmActive(unit))
                {
                    lFire.SetValue(__instance, false);
                    if (Time.time - lastEcmLog > 5f) { lastEcmLog = Time.time; Plugin.Log.LogInfo("P220 laser: held fire, ECM active"); }
                    return;
                }
                var tr = __instance.transform; var dt = lDir.GetValue(__instance) as Transform; if (dt == null) return;
                var tt = lTargetT?.GetValue(__instance) as Transform;
                var target = tt != null ? tt.position : tr.position + tr.forward * 20000f;
                var v = target - tr.position;
                var dir = Vector3.RotateTowards(tr.forward, v, (float)lMaxAngle.GetValue(__instance) * Mathf.Deg2Rad, 0f).normalized;
                float len = Vector3.Angle(dir, v) < 1f ? v.magnitude : 20000f;
                var part = HitsSelf(unit, dt.position, dir, Mathf.Min(len, 400f));
                if (part == null) return;
                lFire.SetValue(__instance, false);   // this tick runs as "not firing": beam off, no damage
                if (Time.time - lastGuardLog > 2f) { lastGuardLog = Time.time; Plugin.Log.LogInfo("P220 laser: held fire, beam would cross " + part.name); }
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser guard: " + e.Message); }
        }
        static float lastEcmLog; static Type jamT; static FieldInfo jLast, jAircraft;
        static readonly Dictionary<int, List<Behaviour>> jammersOf = new Dictionary<int, List<Behaviour>>();
        static readonly Dictionary<int, float> jammerScan = new Dictionary<int, float>();
        // a stock RadarJammer is enabled while it is being fired and switches itself off 0.1 s after the last Fire()
        internal static bool EcmActive(Component unit)
        {
            if (jamT == null) { jamT = R.T("RadarJammer"); jLast = jamT?.GetField("lastActivated", F); jAircraft = R.T("Countermeasure")?.GetField("aircraft", F) ?? jamT?.GetField("aircraft", F); }
            if (jamT == null || jLast == null) return false;
            int id = unit.GetInstanceID();
            if (!jammersOf.TryGetValue(id, out var list) || !jammerScan.TryGetValue(id, out var t) || Time.time - t > 2f)
            {
                list = new List<Behaviour>();
                foreach (var o in UnityEngine.Object.FindObjectsOfType(jamT))
                {
                    var b = o as Behaviour; if (b == null) continue;
                    var ac = jAircraft?.GetValue(b) as Component;
                    if (ReferenceEquals(ac, unit) || (ac == null && b.transform.IsChildOf(unit.transform))) list.Add(b);
                }
                jammersOf[id] = list; jammerScan[id] = Time.time;
            }
            foreach (var b in list)
                if (b != null && b.enabled && jLast.GetValue(b) is float last && Time.timeSinceLevelLoad - last < 0.25f) return true;
            return false;
        }
        internal static Component HitsSelf(Component unit, Vector3 origin, Vector3 dir, float len)
        {
            if (len < 0.3f) return null;
            var far = origin + dir * len;
            foreach (var hit in Physics.RaycastAll(far, -dir, len - 0.05f, ~exclusionMask))
            { var p = Own(unit, hit.collider); if (p != null) return p; }
            foreach (var hit in Physics.RaycastAll(origin, dir, len, ~exclusionMask))
            { var p = Own(unit, hit.collider); if (p != null) return p; }
            return null;
        }
        static Component Own(Component unit, Collider c)
        {
            if (c == null) return null;
            var p = c.GetComponentInParent(unitPartT);
            if (p != null && ReferenceEquals(fParentUnit.GetValue(p), unit)) return p;
            if (c.transform.IsChildOf(unit.transform)) return c;
            return null;
        }

        static bool Ours(Component turret) { var u = R.Get(turret, "attachedUnit") as Component; return u != null && u.name.StartsWith("P220Primrose"); }

        static void PostAttach(Component __instance)
        {
            try { if (Ours(__instance) && __instance.GetComponent<ThornRest>() == null) __instance.gameObject.AddComponent<ThornRest>().turret = __instance; }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser rest: " + e.Message); }
        }

        // whether the turret can put its beam on a point: inside its firing cone, within the gimbal's elevation limit
        // (175 deg off the tail), and with no part of the airframe (or terrain) in the way
        internal enum Arc { Clear, OutOfArc, Blocked }
        internal static Arc Check(Component turret, Vector3 point, float targetRadius)
        {
            var el = R.Get(turret, "elevationTransform") as Transform; var origin = el != null ? el.position : turret.transform.position;
            var v = point - origin; float dist = v.magnitude; if (dist < 1f) return Arc.Clear;
            float maxEl = R.Get(turret, "maxElevation") is float mx ? mx : 90f;
            // the pod gimbal rolls about the turret's up axis (aft); elevation counts from straight down (0) to aft (-90)
            if (Vector3.Angle(turret.transform.up, v) > 90f + (R.Get(turret, "minElevation") is float mn ? -mn : 90f)) return Arc.OutOfArc;
            var cones = R.Get(turret, "firingCones");
            if (coneCheck != null && cones != null)
            {
                var args = new object[] { cones, v, null };
                if (!(bool)coneCheck.Invoke(null, args)) return Arc.OutOfArc;
            }
            var dir = v / dist;
            if (Physics.Linecast(origin, origin + dir * Mathf.Min(dist, 200f), out var hit, ~exclusionMask)
                && hit.distance < dist - (targetRadius + 50f)) return Arc.Blocked;
            var unit = R.Get(turret, "attachedUnit") as Component;
            if (unit != null && unitPartT != null && HitsSelf(unit, origin, dir, Mathf.Min(dist, 400f)) != null) return Arc.Blocked;
            return Arc.Clear;
        }

        // The tactical display's turret aiming box puts a dot at the turret's aim error, read in the turret's own axes
        // from the last vector it aimed at. On the pod gimbal those axes roll with the target, so the dot wandered.
        // For the THORN it shows instead how far the current target lies outside what the laser can reach, in the
        // aircraft's axes (left/right, up/down): centred = the beam can be put on it; off centre = past the arc edge by
        // that many degrees; pinned to the edge = the airframe is in the way.
        static void PostAimError(Component __instance, ref Vector2 __result)
        {
            try
            {
                if (!Ours(__instance)) return;
                var ac = R.Get(__instance, "attachedUnit") as Component;
                var target = R.Get(__instance, "target") as Component;
                if (target == null)
                {
                    var wm = R.Get(ac, "weaponManager"); var list = wm != null ? R.Invoke(wm, "GetTargetList") as System.Collections.IList : null;
                    if (list != null && list.Count > 0) target = list[0] as Component;
                }
                if (target == null) { __result = Vector2.zero; return; }
                var el = R.Get(__instance, "elevationTransform") as Transform; var origin = el != null ? el.position : __instance.transform.position;
                var want = target.transform.position - origin;
                var allowed = Allowed(__instance, want);
                var up = ac.transform.up; var right = ac.transform.right;
                var e = new Vector2(Angle(allowed, want, up), Angle(allowed, want, right));
                if (e.sqrMagnitude < 0.01f && Check(__instance, target.transform.position, R.Get(target, "maxRadius") is float rr ? rr : 5f) == Arc.Blocked)
                {
                    var cones = R.Get(__instance, "firingCones") as Array; var axis = __instance.transform.up;
                    if (cones != null && cones.Length > 0) axis = (Vector3)R.Invoke(cones.GetValue(0), "GetDirection");
                    e = new Vector2(Angle(axis, want, up), Angle(axis, want, right));
                    e = e.sqrMagnitude > 0.01f ? e.normalized * 45f : new Vector2(0f, 45f);
                }
                __result = e;
            }
            catch (Exception ex) { Plugin.Log.LogWarning("P220 laser aim box: " + ex.Message); }
        }
        static float Angle(Vector3 self, Vector3 other, Vector3 axis)
        {
            return Vector3.SignedAngle(Vector3.Cross(axis, self), Vector3.Cross(axis, other), axis);
        }
        // the nearest direction the beam can actually point to: inside the firing cone and the gimbal's elevation limit
        static Vector3 Allowed(Component turret, Vector3 want)
        {
            var v = want;
            var cones = R.Get(turret, "firingCones");
            if (coneCheck != null && cones != null) { var args = new object[] { cones, v, null }; coneCheck.Invoke(null, args); if (args[2] is Vector3 a) v = a; }
            float lim = 90f + (R.Get(turret, "minElevation") is float mn ? -mn : 90f);
            var aft = turret.transform.up;
            if (Vector3.Angle(aft, v) > lim) v = Vector3.RotateTowards(aft, v, lim * Mathf.Deg2Rad, 0f) * v.magnitude;
            return v;
        }

        static void PostHud(object __instance, Component aircraft, System.Collections.IList targetList)
        {
            try
            {
                var info = hsInfo.GetValue(__instance) as UnityEngine.Object;
                if (info == null || !(R.Get(info, "shortName") is string sn) || !sn.StartsWith(ThornName)) return;
                var station = hsStation.GetValue(__instance); var turret = R.Invoke(station, "GetTurret") as Component;
                if (turret == null || targetList == null || targetList.Count == 0) return;
                var target = targetList[0] as Component;
                if (target == null || R.Get(target, "disabled") is bool d && d) return;
                float max = 4000f; var req = R.Get(info, "targetRequirements"); if (R.Get(req, "maxRange") is float mr) max = mr;
                float radius = R.Get(target, "maxRadius") is float rr ? rr : 5f;
                var pos = target.transform.position;
                string text;
                // out of arc outranks out of range: no amount of closing helps a target the laser cannot point at
                if (Check(turret, pos, radius) != Arc.Clear) text = "OUT OF ARC";
                else text = Vector3.Distance(pos, aircraft.transform.position) > max ? "OUT OF RANGE" : "SHOOT";
                var hint = hsHint.GetValue(__instance) as Component;
                var tp = hint?.GetType().GetProperty("text");
                if (tp != null && !Equals(tp.GetValue(hint, null), text)) tp.SetValue(hint, text, null);
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser hint: " + e.Message); }
        }

        static void PostSpawnMount(object __instance, Component aircraft, UnityEngine.Object weaponMount)
        {
            try
            {
                if (weaponMount == null || !(R.Get(weaponMount, "jsonKey") is string k) || k != CapKey || aircraft == null) return;
                var ps = R.Invoke(aircraft, "GetPowerSupply") as Component; if (ps == null) return;
                R.T("PowerSupply").GetMethod("ModifyCapacitance", F).Invoke(ps, new object[] { CapPack });
                packs[__instance] = ps;
                Plugin.Log.LogInfo("P220 capacitor pack fitted: +" + CapPack + " capacitor");
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 capacitor pack: " + e.Message); }
        }

        static void PreRemoveMount(object __instance)
        {
            try
            {
                if (!packs.TryGetValue(__instance, out var ps)) return;
                packs.Remove(__instance);
                if (ps != null) R.T("PowerSupply").GetMethod("ModifyCapacitance", F).Invoke(ps, new object[] { -CapPack });
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 capacitor pack: " + e.Message); }
        }
    }

    // Puts the THORN ball at its rest pose (straight aft) when fitted and slews it back there once the turret has had no
    // target for 5 s, at the turret's own traverse and elevation rates (the same way a stock turret stows).
    public class ThornRest : MonoBehaviour
    {
        internal Component turret;
        static FieldInfo fTrav, fElev, fTarget, fManual, fTravRate, fElevRate, fElevT;
        float idle;

        void Start()
        {
            var t = turret.GetType(); const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            fTrav = t.GetField("traverseAngle", F); fElev = t.GetField("elevationAngle", F); fTarget = t.GetField("target", F);
            fManual = t.GetField("manual", F); fTravRate = t.GetField("traverseRate", F); fElevRate = t.GetField("elevationRate", F);
            fElevT = t.GetField("elevationTransform", F);
            if (fTrav == null || fElev == null || fTarget == null || fElevT == null) { Destroy(this); return; }
            fTrav.SetValue(turret, 0f); fElev.SetValue(turret, Thorn.RestElevation); Apply(0f, Thorn.RestElevation);
            idle = Thorn.IdleReturn;
        }

        void Apply(float trav, float elev)
        {
            turret.transform.localEulerAngles = new Vector3(0f, trav, 0f);
            ((Transform)fElevT.GetValue(turret)).localEulerAngles = new Vector3(elev, 0f, 0f);
        }

        void FixedUpdate()
        {
            if (turret == null) { Destroy(this); return; }
            var tgt = fTarget.GetValue(turret) as Component;
            bool busy = (tgt != null && !(R.Get(tgt, "disabled") is bool d && d)) || (fManual?.GetValue(turret) is bool m && m);
            if (busy) { idle = 0f; return; }
            idle += Time.fixedDeltaTime;
            if (idle < Thorn.IdleReturn) return;
            float tr = (float)fTrav.GetValue(turret), el = (float)fElev.GetValue(turret);
            if (Mathf.Abs(tr) < 0.01f && Mathf.Abs(el - Thorn.RestElevation) < 0.01f) return;
            float trRate = fTravRate?.GetValue(turret) is float a ? a : 90f, elRate = fElevRate?.GetValue(turret) is float b ? b : 90f;
            tr = Mathf.MoveTowards(Mathf.DeltaAngle(0f, tr), 0f, trRate * Time.fixedDeltaTime);
            el = Mathf.MoveTowards(el, Thorn.RestElevation, elRate * Time.fixedDeltaTime);
            fTrav.SetValue(turret, tr); fElev.SetValue(turret, el); Apply(tr, el);
        }
    }

    // The taxi light rides the nose gear leg, so while the leg is folded it points up through the cockpit floor. Stock
    // gear lights are simply always on; this one only shines once the gear is down and locked.
    public class GearLight : MonoBehaviour
    {
        internal Component ac;
        Light light; FieldInfo fGear;
        void Start()
        {
            foreach (var l in GetComponentsInChildren<Light>(true)) if (l.name == "gearlight_F") light = l;
            fGear = ac?.GetType().GetField("gearState", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (light == null || fGear == null) Destroy(this);
        }
        void Update()
        {
            if (light == null) { Destroy(this); return; }
            bool on = fGear.GetValue(ac).ToString() == "LockedExtended";
            if (light.enabled != on) light.enabled = on;
        }
    }

    // Everything game-side is reached by reflection so the plugin needs no game assembly references.
    // Tail laser log: what the defensive turret sees, picks, fires at, hits and what becomes of the target, so a missed
    // engagement can be traced in LogOutput.log. Every line starts "P220 laser:". Only the P220's own turret is logged.
    internal static class LaserLog
    {
        private static readonly HashSet<int> seen = new HashSet<int>();
        private static readonly Dictionary<int, int> picked = new Dictionary<int, int>();
        private static readonly Dictionary<int, float> fireStart = new Dictionary<int, float>();
        private static readonly Dictionary<int, float> lastFireLog = new Dictionary<int, float>();
        private static float lastIgnored;
        private const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;

        public static void Patch(Harmony h)
        {
            var t = R.T("Turret"); var l = R.T("Laser");
            P(h, t, "AttachToWeaponManager", null, nameof(PostAttach));
            P(h, t, "Turret_OnDetectTarget", null, nameof(PostDetect));
            P(h, t, "ChooseTarget", nameof(PreChoose), nameof(PostChoose));
            P(h, t, "Turret_OnTargetDisabled", nameof(PreTargetDisabled), null);
            P(h, l, "Fire", null, nameof(PostFire));
            P(h, t, "FixedUpdate", null, nameof(PostTurretUpdate));
        }

        private static void P(Harmony h, Type t, string name, string pre, string post)
        {
            var m = t?.GetMethod(name, F);
            if (m == null) { Plugin.Log.LogWarning("P220 laser: " + name + " not found, not logged"); return; }
            h.Patch(m, pre == null ? null : new HarmonyMethod(typeof(LaserLog), pre), post == null ? null : new HarmonyMethod(typeof(LaserLog), post));
        }

        private static Component Owner(Component c) { return R.Get(c, "attachedUnit") as Component; }
        private static bool Ours(Component c)
        {
            var u = Owner(c); return u != null && u.name.StartsWith("P220Primrose");
        }
        private static void Log(string s) { Plugin.Log.LogInfo("P220 laser: " + s); }
        private static bool AimedAtUs(object unit, Component owner)
        {
            if (unit == null || owner == null || !R.T("Missile").IsInstanceOfType(unit)) return false;
            var id = R.Get(owner, "persistentID"); return id != null && id.Equals(R.Get(unit, "targetID"));
        }
        // range, and angle off the tail (0 = dead astern), from the turret's mount
        private static string Where(Component turret, Component unit)
        {
            var v = unit.transform.position - turret.transform.position;
            var aft = turret.transform.parent != null ? turret.transform.parent.forward : turret.transform.forward;
            return v.magnitude.ToString("F0") + " m, " + Vector3.Angle(aft, v).ToString("F0") + " deg off the tail";
        }

        private static void PostAttach(Component __instance)
        {
            try
            {
                if (!Ours(__instance)) return;
                var dets = R.Get(__instance, "targetDetectors") as System.Collections.ICollection;
                Log("turret fitted: mode " + R.Get(__instance, "targetAcquisitionMode") + ", " + (dets?.Count ?? -1) + " sensor(s), HQ "
                    + (R.Get(Owner(__instance), "NetworkHQ") != null ? "set" : "MISSING") + ", traverse +-" + R.Get(__instance, "traverseRange"));
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser log: " + e.Message); }
        }

        private static void PostDetect(Component __instance, Component unit)
        {
            try
            {
                if (unit == null || !Ours(__instance) || !R.T("Missile").IsInstanceOfType(unit) || !seen.Add(unit.GetInstanceID())) return;
                Log("sees " + unit.name + " at " + Where(__instance, unit) + (AimedAtUs(unit, Owner(__instance)) ? ", aimed at us" : ", not aimed at us (ignored)"));
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser log: " + e.Message); }
        }

        private static void PreChoose(Component __instance, out int __state)
        {
            __state = 0;
            try
            {
                if (!Ours(__instance)) return;
                var list = R.Get(__instance, "potentialTargets") as System.Collections.IEnumerable;
                if (list != null) foreach (var u in list) if (AimedAtUs(u, Owner(__instance))) __state++;
            }
            catch { }
        }

        private static void PostChoose(Component __instance, int __state)
        {
            try
            {
                if (!Ours(__instance)) return;
                var target = R.Get(__instance, "target") as Component;
                int id = target != null ? target.GetInstanceID() : 0, prev;
                picked.TryGetValue(__instance.GetInstanceID(), out prev);
                if (id != prev)
                {
                    picked[__instance.GetInstanceID()] = id;
                    Log(target != null ? "engaging " + target.name + " at " + Where(__instance, target) : "no target");
                }
                else if (target == null && __state > 0 && Time.time - lastIgnored > 2f)
                {
                    lastIgnored = Time.time;
                    Log(__state + " incoming missile(s) seen but none engaged (out of range, outside the arc, or no ammo)");
                }
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser log: " + e.Message); }
        }

        // once a second while the turret has a target: where the target is relative to the mount (az 0 = dead astern,
        // + = right; el + = above), where the turret is actually pointing, and what blocks its 200 m line-of-fire check
        private static readonly Dictionary<int, float> lastAimLog = new Dictionary<int, float>();
        private static void PostTurretUpdate(Component __instance)
        {
            try
            {
                if (!Ours(__instance)) return;
                var target = R.Get(__instance, "target") as Component;
                if (target == null) return;
                float last; int id = __instance.GetInstanceID();
                if (lastAimLog.TryGetValue(id, out last) && Time.time - last < 1f) return;
                lastAimLog[id] = Time.time;
                var mount = __instance.transform.parent != null ? __instance.transform.parent : __instance.transform;
                var d = mount.InverseTransformDirection((target.transform.position - __instance.transform.position).normalized);
                float az = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg, el = Mathf.Asin(Mathf.Clamp(d.y, -1f, 1f)) * Mathf.Rad2Deg;
                var et = R.Get(__instance, "elevationTransform") as Transform;
                string block = "clear";
                RaycastHit hit;
                if (et != null && Physics.Linecast(et.position, et.position + et.forward * 200f, out hit)) block = hit.collider.name + " at " + hit.distance.ToString("F0") + " m";
                var ef = et != null ? mount.InverseTransformDirection(et.forward) : Vector3.zero;
                Log("aim at " + target.name + ": target az " + az.ToString("F0") + " el " + el.ToString("F0") + ", barrel az "
                    + (Mathf.Atan2(ef.x, ef.z) * Mathf.Rad2Deg).ToString("F0") + " el " + (Mathf.Asin(Mathf.Clamp(ef.y, -1f, 1f)) * Mathf.Rad2Deg).ToString("F0")
                    + ", traverse error " + Convert.ToSingle(R.Get(__instance, "traverseError")).ToString("F1") + ", on target " + R.Get(__instance, "timeOnTarget") + " s, line of fire " + block);
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser log: " + e.Message); }
        }

        private static void PreTargetDisabled(Component __instance, Component unit)
        {
            try
            {
                if (unit == null || !Ours(__instance)) return;
                float t0; bool lased = fireStart.TryGetValue(unit.GetInstanceID(), out t0);
                Log(unit.name + " destroyed at " + Where(__instance, unit) + (lased ? " after " + (Time.time - t0).ToString("F1") + " s of fire" : ", never fired on"));
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser log: " + e.Message); }
        }

        private static void PostFire(Component __instance, Component target)
        {
            try
            {
                if (target == null || !Ours(__instance)) return;
                int id = target.GetInstanceID(); float last;
                if (!fireStart.ContainsKey(id)) fireStart[id] = Time.time;
                if (lastFireLog.TryGetValue(id, out last) && Time.time - last < 1f) return;
                lastFireLog[id] = Time.time;
                var hit = R.Get(__instance, "hitTransform") as Transform;
                Log("firing at " + target.name + " (" + (target.transform.position - __instance.transform.position).magnitude.ToString("F0") + " m), beam hitting "
                    + (hit == null ? "nothing" : hit.name + (hit.IsChildOf(target.transform) ? " (the target)" : "")));
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 laser log: " + e.Message); }
        }
    }

    // Thrust reversers: each engine carries a stock Airbrake that swings its four reverser doors open at idle throttle.
    // Real reversers only deploy on the ground, so on this aircraft the doors stay shut (and close again) unless the
    // landing gear is down and locked.
    internal static class Reversers
    {
        // Thrust reversers are the stock Airbrake (doors open at idle throttle). This keeps them shut unless the gear is
        // down and locked and the aircraft is above 60 km/h, and turns a deployed engine into reverse thrust: the engine
        // spools up with the doors (sound and HUD follow its RPM) and pushes back with up to 30% of its thrust.
        const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        const float MinSpeed = 60f / 3.6f, ReverseFraction = 0.30f;
        static FieldInfo fOpen, fSpeed, fTransforms, fBase, fAircraft, fSound, fGear;
        static FieldInfo tjInputs, tjAircraft, tjNozzles, ciThrottle, nzPart, nzThrust;
        static Type abType;
        public static void Patch(Harmony h)
        {
            abType = R.T("Airbrake"); if (abType == null) { Plugin.Log.LogWarning("P220: no Airbrake type, reverser lock off"); return; }
            var t = abType;
            fOpen = t.GetField("openAmount", F); fSpeed = t.GetField("openSpeed", F); fTransforms = t.GetField("transforms", F);
            fBase = t.GetField("baseAngles", F); fAircraft = t.GetField("attachedAircraft", F); fSound = t.GetField("airbrakeSound", F);
            var acT = R.T("Aircraft"); fGear = acT?.GetField("gearState", F);
            var up = t.GetMethod("Update", F);
            if (up == null || fOpen == null || fGear == null) { Plugin.Log.LogWarning("P220: Airbrake fields not found, reverser lock off"); return; }
            h.Patch(up, prefix: new HarmonyMethod(typeof(Reversers), nameof(Pre)), postfix: new HarmonyMethod(typeof(Reversers), nameof(Post)));
            var tj = R.T("Turbojet"); var fu = tj?.GetMethod("FixedUpdate", F);
            tjInputs = tj?.GetField("controlInputs", F); tjAircraft = tj?.GetField("aircraft", F); tjNozzles = tj?.GetField("nozzles", F);
            ciThrottle = R.T("ControlInputs")?.GetField("throttle", F);
            var nz = R.T("JetNozzle"); nzPart = nz?.GetField("part", F); nzThrust = nz?.GetField("thrustTransform", F);
            if (fu == null || tjInputs == null || tjAircraft == null || ciThrottle == null || nzPart == null || nzThrust == null)
            { Plugin.Log.LogWarning("P220: Turbojet fields not found, no reverse thrust"); return; }
            h.Patch(fu, prefix: new HarmonyMethod(typeof(Reversers), nameof(EnginePre)), postfix: new HarmonyMethod(typeof(Reversers), nameof(EnginePost)));
        }
        static bool Ours(Component ac) { return ac != null && ac.name.StartsWith("P220Primrose"); }
        static bool Allowed(Component ac)
        {
            if (fGear.GetValue(ac).ToString() != "LockedExtended") return false;
            return !(R.Get(ac, "speed") is float v) || v > MinSpeed;
        }
        static void Pre(Component __instance, out float __state) { __state = (float)fOpen.GetValue(__instance); }
        static void Post(Component __instance, float __state)
        {
            try
            {
                var ac = fAircraft.GetValue(__instance) as Component;
                if (!Ours(ac) || Allowed(ac)) return;
                float open = Mathf.Max(0f, __state - (float)fSpeed.GetValue(__instance) * Time.deltaTime);
                fOpen.SetValue(__instance, open);
                var ts = fTransforms.GetValue(__instance) as Transform[]; var bs = fBase.GetValue(__instance) as List<Vector3>;
                float max = (float)R.Get(__instance, "maxAngle");
                if (ts != null && bs != null)
                    for (int i = 0; i < ts.Length && i < bs.Count; i++) { ts[i].localEulerAngles = bs[i]; ts[i].Rotate(new Vector3(open * max, 0f, 0f), Space.Self); }
                if (open <= 0f && fSound.GetValue(__instance) is Component snd && snd != null && R.Get(snd, "isPlaying") is bool pl && pl) R.Call(snd, "Stop");
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 reverser: " + e.Message); }
        }
        // how far this engine's reversers are deployed (0..1, the largest of its airbrakes)
        static float Deployed(Component engine)
        {
            float o = 0f;
            foreach (var ab in engine.GetComponents(abType)) o = Mathf.Max(o, (float)fOpen.GetValue(ab));
            return o;
        }
        struct EngineState { public float throttle, open; public object inputs; }
        static void EnginePre(Component __instance, out EngineState __state)
        {
            __state = default(EngineState);
            try
            {
                var ac = tjAircraft.GetValue(__instance) as Component; if (!Ours(ac)) return;
                float open = Deployed(__instance); if (open <= 0.01f) return;
                var inputs = tjInputs.GetValue(__instance); if (inputs == null) return;
                float thr = (float)ciThrottle.GetValue(inputs);
                __state = new EngineState { throttle = thr, open = open, inputs = inputs };
                ciThrottle.SetValue(inputs, Mathf.Max(thr, open));          // the engine spools up as the doors open
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 reverse thrust: " + e.Message); }
        }
        static void EnginePost(Component __instance, EngineState __state)
        {
            if (__state.inputs == null) return;
            try
            {
                ciThrottle.SetValue(__state.inputs, __state.throttle);      // the pilot's throttle stays at idle
                var ac = tjAircraft.GetValue(__instance) as Component;
                var nozzles = tjNozzles.GetValue(__instance) as Array; if (nozzles == null) return;
                foreach (var nz in nozzles)
                {
                    var part = nzPart.GetValue(nz); var tt = nzThrust.GetValue(nz) as Transform;
                    var rb = R.Get(part, "rb") as Rigidbody; if (rb == null || tt == null) continue;
                    // the force the nozzle just applied (JetNozzle.GetTotalThrust only counts afterburners, which this
                    // engine has none of, so read the applied total itself)
                    if (!(R.Get(ac, "LocalSim") is bool ls && ls)) continue;
                    float t = R.Get(nz, "totalThrust") is float f ? f : 0f;
                    if (!(R.Get(nz, "thrustProportion") is float tp && tp > 0f)) continue;
                    // cancel the forward thrust the nozzle just applied and push back with the reverse fraction
                    rb.AddForceAtPosition(-tt.forward * t * (1f + ReverseFraction) * __state.open, tt.position);
                }
            }
            catch (Exception e) { Plugin.Log.LogWarning("P220 reverse thrust: " + e.Message); }
        }
    }

    // Interior damage (0.4.7): the cargo bay and cabin liner materials use the stock AircraftSkin shader with their own
    // maps, like the skin. The game only passes a part's health to the FIRST material of its damage renderers (that slot
    // also takes the livery), and no stock aircraft has damage maps inside, so there is no stock route for this: the part's
    // health is copied to its interior materials whenever the game updates it.
    internal static class Interior
    {
        const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        static FieldInfo fDmg, fRenderers, fHp, fUnit;
        static readonly Dictionary<int, List<Material>> mats = new Dictionary<int, List<Material>>();
        public static void Patch(Harmony h)
        {
            var up = R.T("UnitPart");
            fDmg = up?.GetField("damageMaterial", F); fHp = up?.GetField("hitPoints", F); fUnit = up?.GetField("parentUnit", F);
            fRenderers = R.T("DamageMaterial")?.GetField("renderers", F);
            var ad = up?.GetMethod("ApplyDamage", F); var rp = up?.GetMethod("Repair", F);
            if (ad == null || fDmg == null || fHp == null || fRenderers == null || fUnit == null) { Plugin.Log.LogWarning("P220: UnitPart fields not found, interior damage off"); return; }
            h.Patch(ad, postfix: new HarmonyMethod(typeof(Interior), nameof(Post)));
            if (rp != null) h.Patch(rp, postfix: new HarmonyMethod(typeof(Interior), nameof(Post)));
        }
        static void Post(Component __instance)
        {
            try
            {
                if (__instance == null) return;
                var unit = fUnit.GetValue(__instance) as Component;
                if (unit == null || !unit.name.StartsWith("P220Primrose")) return;
                int id = __instance.GetInstanceID();
                if (!mats.TryGetValue(id, out var list))
                {
                    list = new List<Material>();
                    var rs = new List<Renderer>();
                    if (fRenderers.GetValue(fDmg.GetValue(__instance)) is System.Collections.IEnumerable e) foreach (var o in e) if (o is Renderer r && r != null) rs.Add(r);
                    var own = __instance.GetComponent<Renderer>(); if (own != null && !rs.Contains(own)) rs.Add(own);
                    foreach (var r in rs)
                    {
                        var sh = r.sharedMaterials; bool any = false;
                        for (int i = 1; i < sh.Length; i++) if (sh[i] != null && (sh[i].name.StartsWith("P220_bay") || sh[i].name.StartsWith("P220_lining"))) any = true;
                        if (!any) continue;
                        var ms = r.materials;   // per-renderer copies, as the game makes for the skin
                        for (int i = 1; i < ms.Length; i++) if (ms[i] != null && (ms[i].name.StartsWith("P220_bay") || ms[i].name.StartsWith("P220_lining"))) list.Add(ms[i]);
                    }
                    mats[id] = list;
                }
                if (list.Count == 0) return;
                float hp = (float)fHp.GetValue(__instance);
                foreach (var m in list) if (m != null) m.SetFloat("_HitPoints", hp);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("P220 interior: " + ex.Message); }
        }
    }

    internal static class R
    {
        private static readonly Dictionary<string, Type> types = new Dictionary<string, Type>();
        private static readonly Dictionary<string, MemberInfo> members = new Dictionary<string, MemberInfo>();
        private const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        public static Type T(string name)
        {
            Type t;
            if (types.TryGetValue(name, out t)) return t;
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                t = a.GetType(name);
                if (t != null) break;
            }
            types[name] = t;
            return t;
        }

        public static object Get(object o, string name)
        {
            if (o == null) return null;
            var t = o.GetType();
            string key = t.FullName + "." + name;
            MemberInfo m;
            if (!members.TryGetValue(key, out m))
            {
                for (var tt = t; tt != null && m == null; tt = tt.BaseType)
                {
                    m = tt.GetField(name, F | BindingFlags.DeclaredOnly);
                    if (m == null) m = tt.GetProperty(name, F | BindingFlags.DeclaredOnly);
                }
                members[key] = m;
            }
            try
            {
                var f = m as FieldInfo;
                if (f != null) return f.GetValue(o);
                var p = m as PropertyInfo;
                if (p != null) return p.GetValue(o, null);
            }
            catch { }
            return null;
        }

        public static float Fl(object o, string name)
        {
            var v = Get(o, name);
            if (v is float) return (float)v;
            if (v is int) return (int)v;
            if (v is bool) return (bool)v ? 1f : 0f;
            if (v != null && v.GetType().IsEnum) return Convert.ToInt32(v);
            return float.NaN;
        }
        public static float Num(object o) { if (o is float) return (float)o; if (o is int) return (int)o; return 0f; }
        public static Component Comp(Transform t, string type)
        {
            foreach (var c in t.GetComponents<Component>()) if (c != null && c.GetType().Name == type) return c;
            return null;
        }
        // jointed parts are moved out from under the aircraft at spawn: search the aircraft and every part
        public static List<Transform> Roots(Component ac)
        {
            var l = new List<Transform> { ac.transform };
            if (Get(ac, "partLookup") is System.Collections.IEnumerable parts)
                foreach (var p in parts) if (p is Component c && !l.Contains(c.transform)) l.Add(c.transform);
            l.RemoveAll(t => l.Exists(r => r != t && t.IsChildOf(r)));
            return l;
        }

        public static void Call(object o, string name) => Invoke(o, name);

        public static object Invoke(object o, string name)
        {
            if (o == null) return null;
            var m = o.GetType().GetMethod(name, F, null, Type.EmptyTypes, null);
            return m != null ? m.Invoke(o, null) : null;
        }

        private static PropertyInfo staticProp;
        public static object Static(string type, string name)
        {
            if (staticProp == null)
            {
                var t = T(type);
                if (t == null) return null;
                staticProp = t.GetProperty(name, BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                if (staticProp == null) return null;
            }
            return staticProp.GetValue(null, null);
        }
    }
}
