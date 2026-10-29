P220 Primrose
=============

EARLY ALPHA. Expect rough edges: no textures yet, blocked-out interiors and stats that are still being tuned.

The P220 Primrose is a domestically built twin-engine airliner flown by the airline Primeva Link (PLINK). Some airframes have been pressed into military service in medical transport, radar and light cargo roles. This mod adds the airborne early warning conversion as a flyable aircraft for Nuclear Option.

Requirements
------------
- Nuclear Option
- BepInEx 5 (Mono, x64): https://github.com/BepInEx/BepInEx/releases
- Blueprinter: https://github.com/nikkorap/NOBlueprinter-Releases

Install
-------
1. Install BepInEx 5 and Blueprinter.
2. Download P220Primrose.dll from the releases page.
3. Put it in Nuclear Option\BepInEx\plugins.
4. Start the game. The P220 Primrose is offered from the medium hangar and on runways.

The mod is a single file. It needs nothing else from this repository.

The aircraft
------------
- Full-size twin-engine airliner with working flaps, slats, spoilers, ailerons, elevators, rudders and landing gear.
- GlobalEye-style dorsal radar on two swept pylons.
- Tail-mounted defensive laser turret. It only engages missiles aimed at the aircraft and covers 135 degrees either side of the tail. It draws from the aircraft's capacitor.
- Rear weapons bay with one pair of doors and two sides (Bay Left and Bay Right), each with the Medusa's internal bay weapons.
- One wing pylon per side.
- Radar jammer and flare dispenser (Medusa values for now).
- Four crew: two on the flight deck and two in the cabin. There are no ejection seats. The forward doors are thrown clear and the crew bail out with parachutes.
- Windscreen and ten rows of cabin windows look into blocked-out interiors.

Hangar spawning
---------------
An airliner is taller than the medium hangar door. When the P220 spawns in a hangar it comes out at full length and span but squashed to 68% of its height. Once it has rolled 60 m from the spawn point it grows back to full height over 12 seconds. Runway and air spawns, the hangar preview and the encyclopedia all show it at full size.

What the plugin does
--------------------
src/ is the full source of P220Primrose.dll. It carries the Blueprinter bundle (the aircraft itself) and adds what the bundle can't do on its own. Everything game-side is reached by reflection, and all of it only touches the P220.

- Hangar squash and regrow (above). While squashed, the aircraft is kept as one rigid body with its correct mass and centre of mass, and is split into its damage parts once it reaches full height.
- Laser log: lines starting "P220 laser:" in BepInEx\LogOutput.log record what the tail laser sees, what it engages, where it is aiming, what it hits and what it destroys.

Building from source
--------------------
- art/scripts builds the model in Blender: a220_parts.py, then export_a220.py writes the FBX and part layout. render_preview.py renders preview shots.
- unity/Editor/A220Builder.cs assembles the prefab, mounts and definition in a Blueprinter project (from a copy of the stock Medusa). Build the bundle with Blueprinter > Mod Builder.
- Copy the .nobp next to src/P220Primrose.csproj and run: dotnet build -c Release -p:GameDir="<your Nuclear Option folder>"
