# P220 Primrose

A twin-engine airliner of the airline Primeva Link (P-LINK), converted for military service, for Nuclear Option. It carries a dorsal AEW radar, a rear weapons bay, wing pylons and a defensive laser in the tail.

![Hangar](docs/images/1_hangar.png)

## Requirements

- Nuclear Option 0.34.2
- [BepInEx 5](https://github.com/BepInEx/BepInEx/releases) (Mono, x64)
- [Blueprinter](https://github.com/nikkorap/NOBlueprinter-Releases) 2.0.1 or newer

## Install

Download `P220Primrose.dll` from the [releases page](../../releases) and put it in `Nuclear Option\BepInEx\plugins`. The mod is one file.

## The aircraft

- SpectralEye AEW Radar, rear weapons bay (Bay Left and Bay Right), wing pylons and a Capacitor Pack option.
- THORNE Airborne Laser in the tail cone: shoots down missiles coming from below and behind.
- Radar jammer and flares. Four crew who bail out through the forward doors.
- The fin folds to fit the medium hangar and unfolds once the aircraft has taxied out.
- Four liveries: P-LINK Demonstrator, Primeva Link Service, PALA Air Force Grey and Primevan Royal Family (both PALA only). Workshop livery tag: `P220 Primrose`.

![P-LINK Demonstrator](docs/images/2_demonstrator.png)
![Primeva Link Service](docs/images/3_primeva_link_service.png)
![PALA Air Force Grey](docs/images/4_pala_air_force_grey.png)
![Primevan Royal Family](docs/images/6_primevan_royal_family.png)
![Bay release](docs/images/5_bay_release.png)

## Livery Bundle

`Livery Bundle/` has the complete exterior as an FBX with the in-game texture layout, the surface maps, a UV layout overlay and the four shipped liveries. Import `P220 Exterior.fbx` into Blender and paint on the skin. See `Livery Bundle/README.txt`.

## Source

`src/` is the plugin, `unity/Editor` builds the prefab in a Blueprinter project, and `art/scripts` builds the model and textures in Blender (`art/scripts/livery/export_livery_bundle.py` writes the Livery Bundle). Build with `dotnet build -c Release -p:GameDir="<your Nuclear Option folder>"` after copying the `.nobp` next to `src/P220Primrose.csproj`.

## Licence

MIT. See [LICENSE](LICENSE) and [CREDITS.txt](CREDITS.txt).
