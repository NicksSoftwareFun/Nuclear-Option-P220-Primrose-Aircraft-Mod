using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace P220Primrose
{
    // Flight deck moving parts and lamps of the P220 you are flying. Read-only: it reads the game's own flight, engine,
    // fuel, damage and weapon state, slides the rudder pedals and switches the annunciator cells on the tac screen page.
    // Cells with a stock signal (gear, brake, missile, radar, mode, engines) are driven by the stock HUD apps on that page.
    public class P220Panel : MonoBehaviour
    {
        private class Pedal { public Transform t; public Vector3 rest; public float pos; }

        private Type hudType, fuelTankType, unitPartType, jammerType, laserType, bayType, airbrakeType, imageType;
        private FieldInfo hudInstance;
        private Component aircraft;
        private readonly Dictionary<string, Pedal> pedals = new Dictionary<string, Pedal>();
        private readonly Dictionary<string, Behaviour> lamps = new Dictionary<string, Behaviour>();
        private Component eng1, eng2;
        private readonly List<Component> tanks = new List<Component>(), jammers = new List<Component>(), lasers = new List<Component>(),
                                         bays = new List<Component>(), airbrakes = new List<Component>(), hydParts = new List<Component>(), elecParts = new List<Component>();
        private float nextUpdate, lastUpdate, nextLampScan;
        private bool reported, failed;

        private static readonly string[] HydNames = { "wing", "aileron", "flap", "elevator", "rudder", "hstab", "vstab", "spoiler" };
        private static readonly string[] ElecNames = { "fuselage", "cockpit", "nose" };

        private void Update()
        {
            if (Time.unscaledTime < nextUpdate) return;
            float dt = Mathf.Clamp(Time.unscaledTime - lastUpdate, 0.001f, 0.5f);
            lastUpdate = Time.unscaledTime; nextUpdate = Time.unscaledTime + 1f/30f;
            try
            {
                var ac = PlayerAircraft();
                if (ac == null || !ac.name.StartsWith("P220Primrose")) { aircraft = null; return; }
                if (ac != aircraft) Bind(ac);
                if (Time.unscaledTime >= nextLampScan) { nextLampScan = Time.unscaledTime + 2f; ScanLamps(); }
                Drive(dt);
                if (!reported && lamps.Count > 0)
                {
                    reported = true;
                    Plugin.Log.LogInfo("P220 panel on " + ac.name + ": " + pedals.Count + " pedals, " + lamps.Count + " lamps, engines " + (eng1 != null) + "/" + (eng2 != null)
                        + ", " + tanks.Count + " tanks, " + jammers.Count + " jammers, " + lasers.Count + " lasers, " + bays.Count + " bay doors, "
                        + airbrakes.Count + " airbrakes, " + hydParts.Count + "/" + elecParts.Count + " hyd/elec parts");
                }
            }
            catch (Exception e)
            {
                if (!failed) { failed = true; Plugin.Log.LogWarning("P220 panel stopped: " + e); }
                aircraft = null;
            }
        }

        private Component PlayerAircraft()
        {
            if (hudType == null)
            {
                hudType = R.T("CombatHUD"); fuelTankType = R.T("FuelTank"); unitPartType = R.T("UnitPart"); jammerType = R.T("RadarJammer");
                laserType = R.T("Laser"); bayType = R.T("BayDoor"); airbrakeType = R.T("Airbrake"); imageType = R.T("UnityEngine.UI.Image");
                if (hudType != null)
                    for (var t = hudType; t != null && hudInstance == null; t = t.BaseType)
                        hudInstance = t.GetField("i", BindingFlags.Static | BindingFlags.Public | BindingFlags.FlattenHierarchy);
            }
            if (hudInstance == null) return null;
            var hud = hudInstance.GetValue(null);
            return hud == null ? null : R.Get(hud, "aircraft") as Component;
        }

        private void Bind(Component ac)
        {
            aircraft = ac; pedals.Clear(); lamps.Clear(); reported = false; eng1 = eng2 = null;
            foreach (var l in new[] { tanks, jammers, lasers, bays, airbrakes, hydParts, elecParts }) l.Clear();
            nextLampScan = 0f;
            var roots = R.Roots(ac);
            foreach (var r in roots) foreach (var t in r.GetComponentsInChildren<Transform>(true))
            {
                if (t.name.StartsWith("P220_pedal_")) pedals[t.name.Substring(11)] = new Pedal { t = t, rest = t.localPosition };
                if (t.name == "engine_1") eng1 = R.Comp(t, "Turbojet");
                if (t.name == "engine_2") eng2 = R.Comp(t, "Turbojet");
            }
            foreach (var r in roots)
            {
                if (fuelTankType != null) tanks.AddRange(r.GetComponentsInChildren(fuelTankType, true));
                if (jammerType != null) jammers.AddRange(r.GetComponentsInChildren(jammerType, true));
                if (laserType != null) lasers.AddRange(r.GetComponentsInChildren(laserType, true));
                if (bayType != null) bays.AddRange(r.GetComponentsInChildren(bayType, true));
                if (airbrakeType != null) foreach (var a in r.GetComponentsInChildren(airbrakeType, true)) if (!a.name.StartsWith("engine")) airbrakes.Add(a);
                if (unitPartType != null)
                    foreach (var p in r.GetComponentsInChildren(unitPartType, true))
                    {
                        string n = p.name.ToLowerInvariant();
                        if (Array.Exists(HydNames, s => n.StartsWith(s))) hydParts.Add(p);
                        else if (Array.Exists(ElecNames, s => n.StartsWith(s))) elecParts.Add(p);
                    }
            }
        }

        // the tac screen canvas is spawned by the stock Cockpit; its cells are found by name
        private void ScanLamps()
        {
            if (imageType == null) return;
            foreach (var root in new[] { "P220Annun", "P220Lamps" })
            {
                var go = GameObject.Find(root); if (go == null) continue;
                foreach (Transform cell in go.transform)
                {
                    var lit = cell.Find("lit"); if (lit == null) continue;
                    var img = lit.GetComponent(imageType) as Behaviour; if (img != null) lamps[cell.name] = img;
                }
            }
        }

        private void Drive(float dt)
        {
            var ac = aircraft; float now = Time.unscaledTime;
            bool flash = Mathf.Repeat(now * 3.2f, 1f) < 0.5f;
            var inputs = R.Invoke(ac, "GetInputs");
            float yaw = R.Fl(inputs, "yaw"), brake = R.Fl(inputs, "brake"), thr = R.Fl(inputs, "throttle");
            if (float.IsNaN(yaw)) yaw = 0f; if (float.IsNaN(brake)) brake = 0f; if (float.IsNaN(thr)) thr = 0f;
            // ---- rudder pedals: right rudder pushes the right pedal forward and the left one back (PB-22 mechanism)
            foreach (var kv in pedals)
            {
                if (kv.Value.t == null) continue;
                float sgn = kv.Key.EndsWith("R") ? 1f : -1f;
                kv.Value.pos = Mathf.Lerp(kv.Value.pos, 0.06f * sgn * Mathf.Clamp(yaw, -1f, 1f), 1f - Mathf.Exp(-dt * 10f));
                kv.Value.t.localPosition = kv.Value.rest + Vector3.forward * kv.Value.pos;
            }
            float speed = R.Fl(ac, "speed"), alt = R.Fl(ac, "radarAlt");
            if (float.IsNaN(speed)) speed = 0f; if (float.IsNaN(alt)) alt = 0f;
            bool airborne = alt > 4f;
            int gear = (int)R.Fl(ac, "gearState");          // 2 locked down, 3 retracting, 4 extending
            bool gearDown = gear == 2;
            // ---- critical strip
            bool fire1 = EngineFire(eng1), fire2 = EngineFire(eng2);
            foreach (var tk in tanks)
            {
                if (tk == null || R.Fl(tk, "onFire") != 1f) continue;
                if (ac.transform.InverseTransformPoint(tk.transform.position).x < 0f) fire1 = true; else fire2 = true;
            }
            Lamp("crit_FIRE 1", fire1 && flash);
            Lamp("crit_FIRE 2", fire2 && flash);
            Lamp("crit_GEAR", airborne && !gearDown && alt < 150f && speed < 85f && thr < 0.5f && flash);
            float aoa = 0f;
            var rb = ac.GetComponent<Rigidbody>();
            if (rb != null && rb.velocity.sqrMagnitude > 400f)
            {
                var v = ac.transform.InverseTransformDirection(rb.velocity);
                aoa = Mathf.Atan2(-v.y, v.z) * Mathf.Rad2Deg;
            }
            Lamp("crit_STALL", airborne && aoa > 15f && flash);
            float level = R.Num(R.Invoke(ac, "GetFuelLevel"));
            Lamp("crit_FUEL", level < 0.10f);
            Lamp("crit_HYD", Health(hydParts) < 0.6f);
            Lamp("crit_ELEC", Health(elecParts) < 0.6f);
            // ---- shared panel
            Lamp("lamp_FLAP", gearDown);                     // stock flaps follow the gear
            Lamp("lamp_SPD BRK", airborne && brake > 0.1f);
            bool rev = false;
            foreach (var e in new[] { eng1, eng2 })
                if (e != null && airbrakeType != null) foreach (var ab in e.GetComponents(airbrakeType)) if (R.Fl(ab, "openAmount") > 0.05f) rev = true;
            Lamp("lamp_REV", rev);
            bool jam = false; foreach (var j in jammers) if (j != null && R.Fl(j, "jamIntensityCurrent") > 0.01f) jam = true;
            Lamp("lamp_JAMMER", jam);
            bool laser = false;
            foreach (var l in lasers) if (l != null && (R.Fl(l, "fireCommanded") == 1f || Time.time - R.Fl(l, "laserLastFired") < 0.3f)) laser = true;
            Lamp("lamp_LASER", laser);
            bool bay = false; foreach (var b in bays) if (b != null && R.Fl(b, "openAmount") > 0.02f) bay = true;
            Lamp("lamp_BAY", bay);
            Lamp("lamp_APU", !airborne && R.Num(R.Invoke(eng1, "GetRPMRatio")) < 0.05f && R.Num(R.Invoke(eng2, "GetRPMRatio")) < 0.05f);
        }

        private static bool EngineFire(Component e)
        {
            if (e == null) return false;
            return R.Fl(e, "engineFire") == 1f;
        }

        private void Lamp(string name, bool on)
        {
            Behaviour b;
            if (lamps.TryGetValue(name, out b) && b != null && b.enabled != on) b.enabled = on;
        }

        private static float Health(List<Component> parts)
        {
            float worst = 1f;
            foreach (var p in parts)
            {
                if (p == null) { worst = 0f; continue; }
                var det = R.Invoke(p, "IsDetached");
                float h = det is bool && (bool)det ? 0f : R.Fl(p, "hitPoints") / 100f;
                if (!float.IsNaN(h)) worst = Mathf.Min(worst, h);
            }
            return worst;
        }
    }
}
