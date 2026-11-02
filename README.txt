P220 Primrose
=============

EARLY ALPHA. Expect rough edges: one livery so far, the passenger and cargo spaces are still plain, and stats are still being tuned.

The P220 Primrose is a domestically built twin-engine airliner flown by the airline Primeva Link (P-LINK). Some airframes have been pressed into military service. This mod adds the military conversion as a flyable aircraft for Nuclear Option: an airliner with a suite of aircraft survivability equipment, including a rear aspect defensive laser.

Requirements
------------
- Nuclear Option
- BepInEx 5 (Mono, x64): https://github.com/BepInEx/BepInEx/releases
- Blueprinter: https://github.com/nikkorap/NOBlueprinter-Releases

Install
-------
1. Install BepInEx 5 and Blueprinter.
2. Download P220Primrose.dll from the releases page.
3. Put it in Nuclear Option\BepInEx\plugins. If you have the 0.2.7-alpha file there, replace it.
4. Start the game. The P220 Primrose is offered from the medium hangar and on runways.

The mod is a single file. It needs nothing else from this repository.

The aircraft
------------
- Full-size twin-engine airliner with working flaps, slats, spoilers, ailerons, elevators, rudders, thrust reversers and landing gear.
- Flight deck with side sticks, sliding thrust levers, moving rudder pedals, four displays and warning lights.
- First livery, "P-LINK Demonstrator": gloss olive and white with dark red detail lines, stencils and markings, with damage textures and the stock structure and engine materials underneath.
- THORNE Airborne Laser in a scooped hood on the tail cone. It burns down missiles aimed at the aircraft. Its arc covers everything below and behind the aircraft, so roll the belly towards an incoming missile. It can be fired by hand or left to the gunner, and draws on the capacitor while it fires.
- Capacitor Pack: fills the rear weapons bay and adds 75% to the laser's capacitor.
- SpectralEye AEW Radar on two swept pylons on the spine.
- Rear weapons bay with Bay Left and Bay Right hardpoints. Wing pylon options include single and double air-to-air, anti-radiation, heavy air-to-ground and anti-ship missiles, the Genie, a rocket pod, a smoke pod and a jamming pod.
- Radar jammer and flare dispenser.
- Four crew. There are no ejection seats: the forward doors are thrown clear and the crew bail out with parachutes.

Hangar spawning
---------------
The fin is taller than the medium hangar door. When the P220 spawns in a hangar, the upper half of the fin is folded flat to starboard. It folds up once the aircraft has rolled 40 m from the spawn point. Runway and air spawns, the hangar preview and the encyclopedia all show the fin upright.

What the plugin does
--------------------
src/ is the full source of P220Primrose.dll. It carries the Blueprinter bundle (the aircraft itself) and adds what the bundle can't do on its own. Everything game-side is reached by reflection, and all of it only touches the P220.

- Folding fin (above).
- Thrust reversers: they open and give reverse thrust only with the gear down and locked, above 60 km/h.
- THORNE laser: a rest pose straight aft, SHOOT / OUT OF ARC / OUT OF RANGE on the HUD, an aiming box that shows how far a target is outside the arc, and a check that holds fire while the beam would cross the aircraft.
- Capacitor Pack: adds its capacitance when fitted.
- Taxi light only shines with the gear down, rudder pedals slide with yaw input, and the flight deck warning lights.
- Laser log: lines starting "P220 laser:" in BepInEx\LogOutput.log record what the tail laser sees, engages, hits and destroys.

Building from source
--------------------
- art/scripts builds the model in Blender (bpy): p220_parts.py (with p220_structure.py) builds the airframe, and export_p220.py writes the FBX and part layout.
- art/scripts/livery paints the skin textures on the airframe: p220_unwrap.py, p220_geom.py, tex_raster_tb.py, p220_paint.py, p220_dmg_alpha.py, then p220_bake_ao.py. p220_preview.py renders preview shots.
- art/scripts/cockpit builds the flight deck interior (head.py, lib_body.py and layout.py joined into one model script, then build_blend.py export).
- unity/Editor/P220Builder.cs assembles the prefab, mounts, livery and definition in a Blueprinter project (from a copy of the stock Medusa). Build the bundle with Blueprinter > Mod Builder.
- Copy the .nobp next to src/P220Primrose.csproj and run: dotnet build -c Release -p:GameDir="<your Nuclear Option folder>"
