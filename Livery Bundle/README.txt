P220 Primrose Livery Bundle

Everything you need to paint a livery for the P220 Primrose in Blender (or any 3D paint program).
Matches mod version 1.0.0 and later. The gold wheel hubs need 1.0.1.

FILES

P220 Exterior.fbx
  The complete exterior, assembled: landing gear down, doors and bays shut, flaps and slats in, fin upright, in
  metres, with the in-game texture layout. Two objects:
  - "P220 Skin": every surface that takes the livery, as ONE object, including the flaps, slats, spoilers, control
    surfaces, doors, the SpectralEye radar fairing, the laser hood and the wheel hubs. Paint this one.
  - "P220 Details": windows, glass, metal, tyres and fans. A livery does not paint these.
  The skin uses material P220_skin, which points at "P220 Base.png". Keep the FBX and the PNG files in the same folder.
  The interior and structure are left out.

P220 Base.png
  Blank base colour: plain white with faint panel lines, no markings, 2048 x 2048. Paint over this or over one of
  the shipped liveries.

P220 UV Layout.png
  Texture island outlines on a transparent background, to lay over your work in a 2D editor.

P220 Normals.png, P220 Metallic.png, P220 Roughness.png, P220 Metallic Smoothness (game format).png, P220 AO.png
  The shared surface maps, for previews. A livery does not change these.

Shipped Liveries
  The four liveries that ship with the mod: P-LINK Demonstrator, Primeva Link Service, PALA Air Force Grey and
  Primevan Royal Family.

PAINTING IN BLENDER

1. File > Import > FBX, pick "P220 Exterior.fbx". The aircraft appears with the base colour on the skin.
2. Select "P220 Skin", switch to the Texture Paint workspace and paint on "P220 Base" (or open a shipped livery
   in the Image Editor and swap it into the P220_skin material's image node). Blender only paints the active
   object, and the whole skin is one object, so a fill or a brush stroke reaches every panel.
3. Image > Save As, PNG, 2048 x 2048, sRGB.
4. Upload it as a Workshop livery with the tag "P220 Primrose".

GOOD TO KNOW

- Bundles downloaded before 10 November 2026 had the skin split into 86 separate parts. Blender only paints the
  active object, so flaps, slats, spoilers and other separate panels were easy to miss and showed up white in game.
  Download the bundle again, open your livery PNG on "P220 Skin" and fill the panels you missed.

- A livery only replaces the base colour. Panel lines and rivets in the normal map stay on top of your paint.
- The skin is double-sided in the game, so the inside of a broken panel shows your paint mirrored and in shadow.
  Nothing extra to paint.
- Keep important artwork a few pixels away from the island edges.
- From 1.0.1 the wheel hubs take their colour from a small square in the texture, 48 x 48 pixels centred on
  column 1021, row 616 (counted from the top left). Paint that square to colour the hubs; leave it grey for plain hubs.
