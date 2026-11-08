using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace P220Primrose
{
    // Turns the engine fans. No stock jet shows a turning fan, so this follows the stock ducted fan's convention instead:
    // the real blades while they turn slowly enough to draw, swapped for a blurred disc (the stock ducted-fan blur
    // material) once they turn faster than a frame can show. The spinner with its white spiral keeps turning at a
    // capped rate so the engine always reads as running. A fan turning faster than about a third of the frame rate
    // strobes differently on every monitor, so nothing here is ever drawn turning faster than that.
    public class P220Fans : MonoBehaviour
    {
        const float FanRevsAtMax = 55f;     // full-power fan speed, rev/s (about 3,300 rpm)
        const float BladeLimit = 4f;        // above this the blades give way to the blur disc, rev/s
        const float SpinnerCap = 4f;        // the spinner never turns faster than this on screen, rev/s
        const float BlurTurn = 0.6f;        // slow drift of the blur disc so it does not look painted on, rev/s

        class Fan { public Component engine; public Transform blades, blur, spinner; public float angle, blurAngle, spinAngle; }
        readonly List<Fan> fans = new List<Fan>();
        static MethodInfo rpmRatio;

        public void Setup(Component aircraft)
        {
            var tj = R.T("Turbojet"); if (tj == null) return;
            if (rpmRatio == null) rpmRatio = tj.GetMethod("GetRPMRatio", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic, null, Type.EmptyTypes, null);
            foreach (var e in aircraft.GetComponentsInChildren(tj, true))
            {
                var f = new Fan { engine = e, blades = Find(e.transform, "P220_fan"), blur = Find(e.transform, "P220_fanblur"), spinner = Find(e.transform, "P220_spinner") };
                if (f.blades == null) continue;
                fans.Add(f);
            }
            if (fans.Count == 0) enabled = false;
        }

        static Transform Find(Transform t, string name)
        {
            foreach (Transform c in t) { if (c.name == name) return c; var r = Find(c, name); if (r != null) return r; }
            return null;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            foreach (var f in fans)
            {
                if (f.engine == null || f.blades == null) continue;
                float ratio = 0f;
                try { ratio = rpmRatio != null ? Mathf.Clamp01((float)rpmRatio.Invoke(f.engine, null)) : 0f; } catch (Exception) { }
                float revs = ratio * FanRevsAtMax;
                bool fast = revs > BladeLimit;
                SetShown(f.blades, !fast); if (f.blur != null) SetShown(f.blur, fast);
                if (!fast) { f.angle = Mathf.Repeat(f.angle + revs * 360f * dt, 360f); Turn(f.blades, f.angle); }
                else if (f.blur != null) { f.blurAngle = Mathf.Repeat(f.blurAngle + BlurTurn * 360f * dt, 360f); Turn(f.blur, f.blurAngle); }
                if (f.spinner != null) { f.spinAngle = Mathf.Repeat(f.spinAngle + Mathf.Min(revs, SpinnerCap) * 360f * dt, 360f); Turn(f.spinner, f.spinAngle); }
            }
        }

        // the fan transforms sit on the engine axis with their local z along it
        static void Turn(Transform t, float deg) { t.localRotation = Quaternion.AngleAxis(deg, Vector3.forward); }

        static void SetShown(Transform t, bool on)
        {
            foreach (Transform c in t) if (c.gameObject.activeSelf != on) c.gameObject.SetActive(on);
        }
    }
}
