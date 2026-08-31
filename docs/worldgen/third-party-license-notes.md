# NeverNether third-party license notes

Branch: `feature/never-nether-worldgen`
Status: active engineering constraint

This file records redistribution / implementation constraints discovered in the exact archives supplied for NeverNether. It is an engineering compliance note, not legal advice.

## Amplified Nether v1.2.15

The supplied archive contains `license.txt` from Stardust Labs. That license permits use and modification on Minecraft servers, but prohibits redistribution of modified versions and also expressly prohibits use of Stardust Labs code/content to configure, test, debug or augment AI/generative systems.

Engineering consequence for NeverFolia:

- Do **not** copy Amplified Nether density-function JSON, noise JSON or other source code/data into NeverFolia.
- Do **not** use the supplied implementation as an AI-assisted transformation source going forward.
- NeverNether terrain generation must be an independently authored NeverFolia implementation based on the project's own approved gameplay/worldgen specification.
- The approved lava level, vertical geometry, cavern sizes, openness profile and other NeverLand decisions remain valid because they are NeverLand design requirements, not copied source implementation.
- If the server later uses Amplified Nether itself in an unmodified or manually modified server-only form, that deployment must remain separate from NeverFolia's distributed source/JAR unless explicit redistribution permission is obtained.

## Other supplied datapacks

Licenses/permissions for Hearths, Dungeons and Taverns, Explorify, Structory: Towers and Repurposed Structures compatibility content must be checked before copying NBT templates, processors, loot tables or other protected files into a distributed NeverFolia artifact.

Until that audit is complete, the repository should contain only:

- NeverLand-authored placement rules/configuration;
- compatibility metadata/IDs necessary for planning;
- independently implemented runtime logic;
- third-party files only when redistribution/modification rights are explicitly verified.
