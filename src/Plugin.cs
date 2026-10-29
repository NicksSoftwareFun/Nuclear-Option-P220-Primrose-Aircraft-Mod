using System;
using System.Collections.Generic;
using System.Reflection;
using BepInEx;
using HarmonyLib;
using UnityEngine;

namespace A220Airliner
{
    // Carries the A220-300 bundle (embedded .nobp, loaded by Blueprinter) and fits the airliner through the medium hangar
    // door: only its height is limiting (the hangar is 80 m wide and 48.7 m deep), so it spawns at full length and span
    // but squashed to 68% height (the largest that clears the 8 m door), and grows to full height over 12 seconds once it
    // has rolled 60 m from its spawn point. Only aircraft that come out of a hangar are squashed; runway and air spawns,
    // the hangar preview and the encyclopedia all show it at full size. No stock aircraft changes size, so this needs
    // the plugin.
    [BepInPlugin("nick.nuclearoption.a220airliner", "P220 Primrose", "0.2.7")]
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
                if (awake == null) { Logger.LogWarning("A220: Aircraft.Awake not found, hangar scaling off"); return; }
                var h = new Harmony("nick.nuclearoption.a220airliner");
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
                Logger.LogInfo("P220 Primrose loaded");
            }
            catch (Exception e) { Logger.LogWarning("A220: hangar scaling not applied: " + e.Message); }
        }

        private static void PostAwake(Component __instance)
        {
            try
            {
                if (!__instance.name.StartsWith("A220Airliner") || __instance.GetComponent<A220Grow>() != null) return;
                __instance.gameObject.AddComponent<A220Grow>().ac = __instance;
            }
            catch (Exception e) { Log.LogWarning("A220: scaling setup failed: " + e.Message); }
        }

        // SetLocalSim runs once as a spawned aircraft starts up, before its parts are split out. Decide here whether it
        // came out of a hangar and needs squashing.
        private static void PreLocalSim(Component __instance)
        {
            try { __instance.GetComponent<A220Grow>()?.Spawned(); }
            catch (Exception e) { Log.LogWarning("A220: hangar squash not applied: " + e.Message); }
        }

        private static void PostLocalSim(Component __instance)
        {
            try { __instance.GetComponent<A220Grow>()?.Merge(); }
            catch (Exception e) { Log.LogWarning("A220: hangar squash not applied: " + e.Message); }
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
                var g = body.GetComponent<A220Grow>();
                if (g != null && g.Growing) g.SetMass();
            }
            catch (Exception e) { Log.LogWarning("A220: mass fix failed: " + e.Message); }
        }

        // A hardpoint mount with its own airframe part (the dorsal radar) is split out onto its own jointed rigidbody when
        // it is fitted. While the aircraft is merged and growing, keep it merged too so it grows with the fuselage; it is
        // split out at full height with the rest.
        private static bool PreSplitPart(Component __instance)
        {
            var unit = R.Get(__instance, "parentUnit") as Component;
            var g = unit != null ? unit.GetComponent<A220Grow>() : null;
            if (g == null || !g.Growing) return true;
            g.Hold(__instance);
            return false;
        }

        // the game's physics LOD must not split the airframe back into jointed parts while it is growing
        private static bool PreComplex(Component __instance)
        {
            var g = __instance.GetComponent<A220Grow>();
            return g == null || !g.Growing;
        }
    }

    public class A220Grow : MonoBehaviour
    {
        private const float SpawnScale = 0.68f;    // height only: full height 11.42 m, so 7.77 m at spawn under the 8 m door
        private const float GrowDistance = 60f;    // metres rolled from the spawn point before growing starts
        private const float GrowTime = 12f;        // seconds from spawn height to full height
        private const float WheelDrop = 3.77f;     // full size: aircraft origin to the bottom of the main wheels

        private class Gear { public Component c; public float radius, travel; public Transform cast; }

        internal Component ac;
        private Rigidbody rb;
        private float scale = 1f, growStart = -1f;
        private Vector3 spawn;
        private bool decided;
        private readonly List<Gear> gears = new List<Gear>();
        private readonly List<Component> held = new List<Component>();
        private static FieldInfo fRadius, fTravel, fPatch, fCast, fBump;

        public bool Growing { get; private set; }

        public void Spawned()
        {
            if (decided) return;
            decided = true;
            if (R.Get(ac, "NetworkspawningHangar") as Component == null) { Destroy(this); return; }
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
            // nothing is split out yet, so squashing the root squashes the whole airframe; while Growing is set the
            // game's own call to split the parts out is skipped
            Growing = true;
            float y0 = transform.position.y;
            Resize(SpawnScale, true);
            float gap = SettleOnFloor();
            spawn = Global();
            Plugin.Log.LogInfo("A220 squashed to " + SpawnScale + " height for the hangar (lowered " + (y0 - transform.position.y).ToString("F2") + " m, wheels were " + gap.ToString("F2") + " m off the floor)");
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
                var bottom = g.cast.position - up * (g.travel * scale);
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
            Plugin.Log.LogInfo("A220 merged for the squashed phase: " + rb.mass.ToString("F0") + " kg, CoM z " + rb.centerOfMass.z.ToString("F2") + " m");
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
            Resize(SpawnScale + (1f - SpawnScale) * Mathf.SmoothStep(0f, 1f, k), Local());
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
            Plugin.Log.LogInfo("A220 at full height");
            Destroy(this);
        }

        private bool Local() => R.Get(ac, "LocalSim") is bool b && b;

        // position relative to the world origin, unaffected by the game's floating origin shifts
        private Vector3 Global()
        {
            var o = R.Static("Datum", "origin") as Transform;
            return o != null ? transform.position - o.position : transform.position;
        }

        private void SetGear(float s)
        {
            foreach (var g in gears)
            {
                if (g.c == null) continue;
                fRadius.SetValue(g.c, g.radius * s);
                fTravel.SetValue(g.c, g.travel * s);
                if (fPatch != null) fPatch.SetValue(g.c, g.radius * s * 0.5f);
            }
        }

        // Stretches the merged airframe upward from the ground point under the main wheels so it stays on its wheels. On other
        // machines the position comes from the network, so after spawning only the scale changes there.
        private void Resize(float s, bool move)
        {
            float f = s / scale;
            var ground = transform.position - transform.up * (WheelDrop * scale);
            transform.localScale = new Vector3(1f, s, 1f);
            if (move)
            {
                var p = ground + (transform.position - ground) * f;
                if (rb != null) rb.position = p;
                transform.position = p;
                Physics.SyncTransforms();
                if (rb != null) { rb.ResetInertiaTensor(); SetMass(); }
            }
            SetGear(s);
            scale = s;
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
            var u = Owner(c); return u != null && u.name.StartsWith("A220Airliner");
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

        public static void Call(object o, string name) => Invoke(o, name);

        public static object Invoke(object o, string name)
        {
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
