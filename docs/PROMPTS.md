# 캐릭터 그림 만들기 (Gemini 프롬프트)

캐릭터의 **서 있는 그림 1장**(예: `hokora/sprites/reimu/idle_0.png` 또는 처음 뽑은 기준 그림)을 첨부하고,
아래 공통 프롬프트의 `[시트 내용]` 자리에 A·B·C 중 하나를 넣어 시트를 뽑습니다.
뽑은 시트는 가져오기 도구에 `--preset` 으로 넣으면 이름이 자동으로 붙습니다.

```
python tools/import_sheet.py 시트A.png <캐릭터> --preset move
python tools/import_sheet.py 시트B.png <캐릭터> --preset react
python tools/import_sheet.py 시트C.png <캐릭터> --preset life
```

| 시트 | 장면 (순서) | 누가 필요 |
| --- | --- | --- |
| A. 이동 (`move`) | 서기 2, 깜빡 1, 걷기 6 | 새 캐릭터 |
| B. 반응 (`react`) | 앉기 2, 던져짐 1, 쓰다듬기 4, 잡힘 3 | 새 캐릭터 |
| C. 생활 (`life`) | 낮잠 2, 손 흔들기 2, 특기 2, 뛰기 2, 붙잡힘 1 | 모든 캐릭터 |

**배경색**: 기본은 초록(`#00FF00`)입니다. 캐릭터에 초록이 많으면(사나에 머리, 요우무 옷) 프롬프트의 `#00FF00` 과
`green` 을 **자홍 `#FF00FF` / `magenta`** 로 바꿔서 뽑으세요. 가져오기 도구가 배경색을 알아서 판별합니다.

AI가 칸 순서를 틀리게 그리면 `--names` 로 직접 이름을 붙이고, 이상한 장면은 이름 자리에 `-` 를 써서 뺍니다.

## 공통 프롬프트

```
Using the attached image as the exact character and style reference, create ONE sprite sheet
of this same character. Keep the character identical in every frame: same face, same outfit,
same colors, same thick outline, same chibi plush proportions, same size and scale.
The head must stay the same size in every frame. Consecutive frames of one action must differ
only slightly, like frames of a real animation. Every frame is full body, facing slightly to
the viewer's right, standing on the same bottom line of its row, with clear green space
between frames so that no two frames touch or overlap. Read order: left to right, top to bottom.

[시트 내용]

Background: solid flat pure green (#00FF00) everywhere. No grid lines, no borders,
no numbers, no text, no shadows.
```

## 시트 A: 이동

```
Layout: 3 rows x 3 columns, 9 frames.
Row 1: 1. Standing still, arms relaxed. 2. Chest very slightly raised (breathing in). 3. Same as 1 with eyes closed (blink).
Row 2 (walking to the right): 4. Left foot forward touching the ground. 5. Left foot flat, body slightly lower. 6. Right foot passing under the body, body highest.
Row 3: 7. Right foot forward touching the ground. 8. Right foot flat, body slightly lower. 9. Left foot passing under the body, body highest.
```

## 시트 B: 반응

```
Layout: 3 rows: 3 frames, 4 frames, 3 frames (10 frames).
Row 1: 1. Sitting on the ground, legs stretched forward, hands on the lap. 2. Same, looking to the side. 3. Tumbling in the air, surprised face.
Row 2 (happy when petted): 4. Crouching, eyes closed in ^^ shape. 5. Jumping up, arms raised. 6. Top of the jump, very happy. 7. Landing, knees bent.
Row 3 (picked up, flailing): 8. Surprised, arms up, legs apart. 9. Arms and legs swapped. 10. Arms out to the sides.
```

## 시트 C: 생활

```
Layout: 3 rows x 3 columns, 9 frames.
Row 1:
 1. Sitting on the ground and sleeping: eyes closed, head tilted, peaceful face, small drool bubble.
 2. Same as 1, head tilted a little more (breathing out).
 3. Standing and waving the right hand high, happy smile.
Row 2:
 4. Same as 3, hand waved to the other side.
 5. [캐릭터 특기] - start of the action.
 6. [캐릭터 특기] - end of the action.
Row 3:
 7. Running fast to the right, body leaning forward, left leg forward, small sweat drop.
 8. Running fast to the right, right leg forward.
 9. Caught: flinching with surprised eyes, sweat drop, both hands up.
```

| 캐릭터 | `[캐릭터 특기]` |
| --- | --- |
| 레이무 | `Sweeping the ground with a bamboo broom` |
| 마리사 | `Holding a small bag full of gold coins with a mischievous grin` |
| 사쿠야 | `Holding up a silver pocket watch (stopping time)` |
| 치르노 | `Throwing a small ice crystal forward with a proud face` |

## 신사 장식 시트

아무 캐릭터 그림을 그림체 참고용으로 첨부합니다.

```
Using the attached image ONLY as an art style reference (thick soft dark-brown outline,
flat colors, cute chibi style), draw 9 small Japanese shrine decoration props as ONE sheet,
3 rows x 3 columns, each prop standing on its own bottom line, clear green space between them:
1. A small cherry blossom tree in full bloom. 2. A stone lantern (toro). 3. A white fox (kitsune) statue sitting.
4. An omikuji rack with white paper fortunes tied on strings. 5. An ema rack with small wooden prayer plaques.
6. A red paper umbrella with a small red bench. 7. A bamboo water basin (temizuya). 8. A wind chime hanging from a small wooden frame.
9. A big donation box (saisen-bako) with a golden coin on top.
Background: solid flat pure green (#00FF00). No text, no shadows, no grid lines.
```

## 새 캐릭터 기준 그림 (1단계)

기존 캐릭터의 서 있는 그림(예: 레이무 `idle_0.png`)을 **그림체 참고용**으로 첨부합니다.
뽑은 기준 그림을 다시 첨부해서 시트 A·B·C 를 뽑습니다.

```
The attached image is ONLY a style reference. Copy its art style exactly: chibi plush doll
proportions (very big round head, small bean-shaped body, stubby arms, round nub feet),
thick soft dark-brown outline, big sparkly eyes, cat-like mouth, soft pink blush, flat colors
with gentle shading. Do NOT copy the reference character's hair, bow, or outfit.

Draw this character instead, standing still, full body, body turned slightly to the viewer's right,
arms relaxed, feet at the bottom, centered, portrait canvas 5:6:
[캐릭터 설명]

Background: solid flat pure [BG]. No shadow, no text, no other objects.
```

| 캐릭터 | 배경 `[BG]` | `[캐릭터 특기]` |
| --- | --- | --- |
| 사나에 | `magenta (#FF00FF)` | `Waving a gohei (white paper wand) overhead, summoning a small swirl of wind (a miracle)` |
| 플랑드르 | `green (#00FF00)` | `Swinging a black twisted wand (Laevatein) with a playful fanged grin` |
| 레밀리아 | `green (#00FF00)` | `Spreading her bat wings wide and pointing forward with a proud, confident smirk` |
| 요우무 | `magenta (#FF00FF)` | `Drawing her long katana in a quick slash, with a sharp sword glint` |

**캐릭터 설명**

- 사나에: `Kochiya Sanae from Touhou Project: long bright green hair with one side lock, a white frog-shaped hair clip on the left, a white snake-shaped hair ornament wrapped around the side lock, green eyes, a white shrine maiden top with blue trim, detached white sleeves with blue trim, a blue skirt with a white frill hem, blue-and-white shoes.`
- 플랑드르: `Flandre Scarlet from Touhou Project: short blonde hair with a small side ponytail on her left, a white mob cap with a red ribbon, red eyes, a small fang, a red vest and red skirt with white frills, a white blouse with short puffy sleeves, a small yellow ascot, red shoes. Wings: two thin black branch-like wings with hanging crystal gems colored red, orange, yellow, cyan, blue and purple (NO green crystals). The wings must stay close to her body.`
- 레밀리아: `Remilia Scarlet from Touhou Project: short light lavender-blue hair, a pale pink mob cap with a red ribbon, red eyes, a small fang, a pale pink dress with short puffy sleeves, red ribbons and white frills, pink shoes, small dark purple bat wings on her back close to her body.`
- 요우무: `Konpaku Youmu from Touhou Project: short silver-white bob hair, a black hairband with a black ribbon bow, blue-gray eyes, a green vest over a white short-sleeved blouse, a green skirt, a small black bow tie, brown shoes, two katanas on her back (one long, one short). Her white ghost half (a round white wispy spirit with a short tail) floats right behind her shoulder, overlapping her body so it touches her.`

## 걷기만 다시 뽑기 (8장)

지금 캐릭터의 서 있는 그림(`hokora/sprites/<캐릭터>/idle_0.png`)을 첨부합니다.
초록 캐릭터(사나에·요우무)는 `#00FF00` / `green` 을 `#FF00FF` / `magenta` 로 바꿉니다.

```
Using the attached image as the exact character and style reference, draw a smooth 8-frame
WALK CYCLE of this same character as ONE sprite sheet.

VERY IMPORTANT - keep these identical in all 8 frames:
- The character always faces the SAME direction as the reference: body and face turned toward
  the viewer's RIGHT at the same 3/4 angle. Never turn the head or body toward the viewer or to the left.
- Same face, same expression, same outfit, same colors, same thick outline, same size and scale.
- The head stays in the same place; only a tiny up-and-down bob is allowed.
- Only the legs and arms move. Walking in place (like on a treadmill), no forward travel.

Layout: 2 rows x 4 columns, 8 frames, read left to right, top to bottom. Every frame full body,
standing on the same bottom line, with clear green space between frames so that no two frames touch.

1. Contact: right foot forward touching the ground with the heel, left foot behind, left arm forward.
2. Down: right foot flat, body slightly lower, left foot starting to lift.
3. Passing: left foot passing under the body, body at its highest, arms at the sides.
4. Up: left foot swinging forward, right heel lifting.
5. Contact: left foot forward touching the ground with the heel, right foot behind, right arm forward.
6. Down: left foot flat, body slightly lower, right foot starting to lift.
7. Passing: right foot passing under the body, body at its highest, arms at the sides.
8. Up: right foot swinging forward, left heel lifting.

Background: solid flat pure green (#00FF00) everywhere, no grid lines, no borders,
no numbers, no text, no shadows.
```

넣을 때는 옛 걷기 그림을 지우고 새 8장으로 바꿉니다.

```
python tools/import_sheet.py 걷기.png reimu --preset walk
```

AI가 8장이 아닌 다른 장수로 그렸으면 다시 뽑는 게 가장 간단합니다.

## 손님 시트 (12장)

손님(세 요정·아야·스이카)은 시트 한 장으로 끝냅니다. 먼저 위의 **새 캐릭터 기준 그림**으로 서 있는 그림을 뽑고,
그 그림을 첨부해서 공통 프롬프트의 `[시트 내용]` 자리에 아래를 넣습니다.

```
Layout: 3 rows x 4 columns, 12 frames.
Row 1: 1. Standing still, arms relaxed. 2. Same, tiny change of expression. 3. Same as 1 with eyes closed (blink). 4. A small polite bow, eyes closed.
Row 2 (walking to the right): 5. Right foot forward. 6. Feet passing, body highest. 7. Left foot forward. 8. Feet passing, body highest.
Row 3: 9. [손님 특기] (start). 10. [손님 특기] (end). 11. Caught red-handed: shocked face with a sweat drop, hands up. 12. Very happy, eyes closed in ^^ shape, one hand raised.
```

| 손님 | `[손님 특기]` |
| --- | --- |
| 서니 밀크 | `Sneaky grin with a finger on her lips (about to play a prank)` |
| 루나 차일드 | `Finger on her lips, "shh" (silencing all sound)` |
| 스타 사파이어 | `Pointing ahead with a small sparkle (she senses something)` |
| 아야 | `Holding a camera up to her face and taking a photo, with a small flash` |
| 스이카 | `Drinking from her purple gourd, cheeks flushed` |

```
python tools/import_sheet.py 아야.png aya --preset guest
```

칸끼리 붙어 있으면 `--grid 3x4` 를 더하면 칸 단위로 나눕니다.

## 전용 의상 (스킨)

색·재질 스킨은 코드로 만들지만, 완전히 다른 옷(유카타·산타 등)은 그림을 뽑아야 합니다.
**같은 캐릭터를 다른 옷으로** 시트 A·B·C·걷기를 모두 뽑아서 `<캐릭터>@<옷>` 이름으로 넣으면,
의상실 뽑기에 **전설** 등급으로 저절로 들어갑니다.

1. 기준 그림: 캐릭터의 `idle_0.png` 를 첨부하고 아래로 서 있는 그림을 한 장 뽑습니다.

```
Using the attached image as the exact character and style reference, draw this SAME character
(same face, same hair, same eyes, same chibi plush proportions, same thick outline) standing still,
full body, turned slightly to the viewer's right, but wearing a different outfit:
[옷 설명]
Background: solid flat pure green (#00FF00). No shadow, no text, no other objects.
```

2. 그 그림을 첨부해서 위의 공통 프롬프트로 시트 A·B·C 와 걷기 시트를 뽑습니다.
3. 넣기 (캐릭터 이름 뒤에 `@옷`):

```
python tools/import_sheet.py 시트A.png reimu@yukata --preset move
python tools/import_sheet.py 시트B.png reimu@yukata --preset react
python tools/import_sheet.py 시트C.png reimu@yukata --preset life
python tools/import_sheet.py 걷기.png reimu@yukata --preset walk
```

| 옷 이름 (`@` 뒤) | 화면 이름 | `[옷 설명]` 예 |
| --- | --- | --- |
| `yukata` | 유카타 | `a summer yukata with a floral pattern, a wide obi sash tied in a bow at the back, wooden geta sandals` |
| `santa` | 산타 | `a red Santa dress with white fluffy trim, a Santa hat, black boots` |
| `pajama` | 잠옷 | `cute pastel pajamas with a matching nightcap, holding a small pillow` |
| `swimsuit` | 수영복 | `a cute one-piece swimsuit with a frilly skirt, a straw hat, a swim ring` |
| `school` | 교복 | `a Japanese sailor school uniform with a red neckerchief, loafers` |

다른 이름도 되지만 화면에는 그 영어 이름 그대로 나옵니다 (`hokora/wardrobe.py` 의 `ART_NAMES` 에 한글 이름 추가).

## 계절 한정 장식 시트 (9개)

`hokora/sprites/props/_preview.png`(지금 장식들)를 그림체 참고용으로 첨부합니다. 초록이 많아서 배경은 자홍입니다.

```
Using the attached image ONLY as an art style reference (thick soft dark-brown outline,
flat colors with gentle shading, cute chibi game-asset style, same scale as those props),
draw 9 small seasonal Japanese decoration props as ONE sheet, 3 rows x 3 columns,
each prop standing on its own bottom line, with clear magenta space between them so nothing touches:
1. A kadomatsu (New Year bamboo and pine decoration in a straw-wrapped base).
2. A cute snowman with a red scarf and a small bucket on its head.
3. A small Christmas tree with colorful ornaments and a gold star on top.
4. A pair of tiny hina dolls (emperor and empress) on a small two-step red stand.
5. Koinobori: three carp streamers (black, red, blue) flying on a tall wooden pole.
6. A tanabata bamboo branch in a small stand, with colorful paper wish strips hanging from it.
7. Three sunflowers in a terracotta pot.
8. Tsukimi: a pyramid of white moon-viewing dango on a small wooden stand, with pampas grass.
9. A carved Halloween jack-o'-lantern pumpkin wearing a small witch hat.
Background: solid flat pure magenta (#FF00FF) everywhere. No text, no shadows, no grid lines, no ground.
```

```
python tools/import_sheet.py 계절장식.png props --names kadomatsu,snowman,xmas_tree,hina,koinobori,tanabata,sunflower,tsukimi,pumpkin --append
```

## 신사 스킨 시트 (4채)

`docs/photo.png`(지금 신사가 나온 사진)를 그림체 참고용으로 첨부합니다.

```
Using the attached image ONLY as an art style reference (thick soft dark-brown outline,
flat colors with gentle shading, cute chibi game-asset style), draw 4 small Japanese shrine buildings
as ONE sheet, 2 rows x 2 columns, all the same size, each standing on its own small stone base
at the bottom of its cell, seen from the front and slightly from the right,
with clear magenta space between them so nothing touches:
1. Moriya Shrine style: a wooden shrine hall with a teal-blue roof, a thick shimenawa rope,
   and two small onbashira log pillars on both sides.
2. A snowy shrine: a red shrine hall with thick white snow piled on the roof, small icicles,
   and a little snow-covered stone lantern beside it.
3. A cherry blossom shrine: a red shrine hall with two small pale-pink cherry trees on both sides
   and petals scattered on the roof.
4. A tiny Scarlet Devil Mansion: a small red-brick western mansion with a clock tower,
   a dark red roof and small bat-shaped decorations.
No people, no animals, no grass, no sky.
Background: solid flat pure magenta (#FF00FF) everywhere. No text, no shadows, no grid lines.
```

```
python tools/import_sheet.py 신사스킨.png shrines --names moriya,snowy,sakura,scarlet --grid 2x2
```

## 새 손님: 니토리 · 코이시 · 테위

손님마다 2장입니다. 먼저 **새 캐릭터 기준 그림** 프롬프트(위)로 서 있는 그림을 뽑고
(그림체 참고로 `hokora/sprites/reimu/idle_0.png` 첨부), 그 그림을 첨부해서 **손님 시트** 프롬프트를 뽑습니다.

| 손님 | 배경 | `[캐릭터 설명]` | `[손님 특기]` |
| --- | --- | --- | --- |
| 니토리 | `magenta (#FF00FF)` | `Kawashiro Nitori from Touhou Project: short blue hair in two small pigtails tied with red bead hair ties, a green cap, blue eyes, a blue-and-teal outfit with many pockets and a round key pendant on the chest, a big green backpack, blue boots.` | `Pulling a wrench and a small gadget out of her backpack, grinning proudly (showing off her inventions)` |
| 코이시 | `magenta (#FF00FF)` | `Komeiji Koishi from Touhou Project: short wavy pale grey-green hair, a black hat with a yellow ribbon, green eyes, a yellow blouse, a dark green skirt with a small flower pattern, a closed purple third eye at her chest connected by thin purple cords that wrap loosely around her body, a soft absent-minded smile.` | `Tiptoeing sneakily with a finger on her lips (9), then popping out with both arms wide and a playful "boo!" face (10)` |
| 테위 | `green (#00FF00)` | `Inaba Tewi from Touhou Project: short wavy black hair, floppy white rabbit ears, red eyes, a short pink dress with a frilly hem, a carrot necklace, bare feet.` | `Holding a small shovel with a mischievous grin (digging a pitfall trap)` |

```
python tools/import_sheet.py 니토리.png nitori --preset guest
python tools/import_sheet.py 코이시.png koishi --preset guest
python tools/import_sheet.py 테위.png tewi --preset guest
```

칸끼리 붙어 있으면 `--grid 3x4` 를 더합니다.

## 홍보 배너 (README·릴리스·SNS)

`docs/photo.png` 와 `docs/characters.png` 를 첨부합니다. 글자는 나중에 코드로 얹으니 그리지 않게 합니다.

```
Using the attached images as the exact character and art style reference (cute chibi plush-style
characters with thick soft outlines), draw a wide banner illustration, aspect ratio 2:1 (1280x640):
the same characters gathered happily around a small red Japanese shrine and a short row of red torii gates,
all standing on top of a Windows taskbar at the bottom of a computer desktop.
Cozy early-evening sky with soft pink and orange clouds, a few cherry blossom petals floating.
Keep the left third of the image calm and mostly empty sky (space for a title).
Do NOT write any text, letters, logos or watermarks anywhere.
```

## 요우무 (8번째 친구) · 유유코 · 미스티아

요우무는 시트 A·B·C·걷기 4장, 유유코·미스티아는 손님 시트 1장씩. 모두 먼저 **기준 그림**을 뽑고 그 그림을 첨부해서 시트를 뽑습니다.
시트 프롬프트에는 위가 잘리지 않게 아래 단락을 꼭 넣습니다 (`[머리 장식]` 자리는 캐릭터에 맞게).

```
IMPORTANT - nothing may be cut off:
- Draw each character a bit smaller, about 75% of its cell height.
- Leave clear empty space ABOVE every head, at least as tall as [머리 장식] itself.
- [머리 장식] must be completely visible in every frame, never touching or crossing the top edge
  of the image or the row above.
- Leave a wide empty margin around the whole sheet on all four sides.
```

| 캐릭터 | 배경 | `[머리 장식]` |
| --- | --- | --- |
| 요우무 | 자홍 | `the hairband bow and the ghost half` |
| 유유코 | 초록 | `the hat` |
| 미스티아 | 초록 | `the hat and the wings` |

- 유유코: `Saigyouji Yuyuko from Touhou Project: chin-length wavy pink hair, a light blue triangular-ghost-cloth cap with a red spiral mark on the front, pink eyes, a light blue kimono-style dress with wavy white trim and wide sleeves, a closed folding fan in her hand, a gentle dreamy smile.`
  손님 특기: `9. Happily eating a big rice ball with both hands. 10. Patting her full round belly with a satisfied smile.`
- 미스티아: `Mystia Lorelei from Touhou Project: short pink hair, a brown mob cap with a small wing ornament, golden-brown eyes, small bird wings on her back (soft brown-purple with pale tips), a brown dress with a white apron front and puffy sleeves, white socks, brown shoes, a cheerful face.`
  손님 특기: `9. Fanning a small charcoal grill of lamprey skewers with a paper fan, smiling. 10. Holding up a steaming grilled skewer proudly.`

### 포장마차 소품 (미스티아)

```
Using the attached image ONLY as an art style reference (thick soft dark-brown outline,
flat colors with gentle shading, cute chibi game-asset style), draw ONE small Japanese food stall (yatai)
on two wooden wheels: a wooden counter with a small charcoal grill and lamprey skewers, a short dark blue
noren curtain with NO letters, two round red paper lanterns hanging from the roof, a small slanted roof,
seen from the front and slightly from the right, standing on the bottom of the image.
No people, no animals, no ground.
Background: solid flat pure green (#00FF00) everywhere. No text, no shadows.
```

```
python tools/import_sheet.py 요우무A.png youmu --preset move
python tools/import_sheet.py 요우무B.png youmu --preset react
python tools/import_sheet.py 요우무C.png youmu --preset life
python tools/import_sheet.py 요우무걷기.png youmu --preset walk
python tools/import_sheet.py 유유코.png yuyuko --preset guest
python tools/import_sheet.py 미스티아.png mystia --preset guest
python tools/import_sheet.py 포장마차.png props --names yatai --append
```

## 전용 의상 — 간편판 (1벌 2장)

시트 4장 대신 **12컷 시트 1장**으로 의상을 만듭니다. 없는 동작(잠자기·잡히기·뛰기 등)은 비슷한 컷으로 대신합니다.
1. 기준 그림: 캐릭터의 `idle_0.png` 를 첨부하고 위 "전용 의상" 기준 그림 프롬프트로 그 옷을 입은 모습을 뽑습니다.
2. 시트: 그 그림을 첨부하고 아래로 12컷을 뽑습니다 (`[특기]` 는 의상에 맞게).

```
Layout: 3 rows x 4 columns, 12 frames, all rows the same height.
Row 1: 1. Standing still, arms relaxed. 2. Same, tiny change of expression. 3. Same as 1 with eyes closed (blink). 4. Sitting on the ground, legs stretched forward, hands on the lap.
Row 2 (walking to the right): 5. Right foot forward. 6. Feet passing, body highest. 7. Left foot forward. 8. Feet passing, body highest.
Row 3: 9. [특기] (start). 10. [특기] (end). 11. Surprised: shocked face with a sweat drop, hands up. 12. Very happy, eyes closed in ^^ shape, one hand raised.
```

```
python tools/import_sheet.py 의상.png reimu@witch --preset outfit
```

| 의상 | 폴더 | `[옷 설명]` | `[특기]` |
| --- | --- | --- | --- |
| 🎃 마녀 레이무 (10월) | `reimu@witch` | `a Halloween witch costume: a big black pointed witch hat with her big red hair bow pinned on it, a short black cape with orange lining over her red-and-white shrine maiden outfit, orange-and-purple striped stockings, holding a small broom` | `Waving the broom like a magic wand, sending out a small pumpkin-shaped sparkle` |
| 🎃 호박 사나에 (10월, 자홍 배경) | `sanae@pumpkin` | `a cute pumpkin costume: a round puffy orange pumpkin dress with a green leaf collar, a small green pumpkin-stem cap on her head, keeping her frog hair clip and snake hair ornament, orange shoes` | `Holding up a small glowing jack-o'-lantern lamp with a big grin, then holding out a basket of candy (trick or treat!)` |
| 🎃 유령 분장 치르노 (10월) | `cirno@obake` | `a cute white bedsheet ghost costume draped over her body, her face showing through a round opening, her blue hair bow on top of the sheet, her ice wings poking out from the sides` | `Raising both arms under the sheet in a spooky "boo!" pose, then giggling with a mischievous face` |

## 장식 2탄 (9개, 자홍 배경)

`hokora/sprites/props/_preview.png` 를 그림체 참고용으로 첨부합니다.

```
python tools/import_sheet.py 장식2.png props --names pond,taiko,bamboo_fence,maneki_neko,yukimi_lantern,maple,suzu,mini_torii,incense --append
```

## 새 친구 메이링 · 손님 레이센

메이링은 요우무와 같은 순서(기준 그림 → 시트 A·B·C·걷기)로, 배경은 자홍입니다. 레이센은 손님 시트(초록 배경)입니다.

- 메이링: `Hong Meiling from Touhou Project: long straight red hair with a thin braid on each side tied with black ribbons, a green beret-style cap with a small gold star badge (no letters), blue-gray eyes, a green Chinese-style long dress (qipao) with side slits over white pants, a calm cheerful face, black shoes.`
  시트 C 특기: `5. Taking a kung-fu stance with one palm forward. 6. A strong palm strike with a small rainbow-colored sparkle.`
- 레이센: `Reisen Udongein Inaba from Touhou Project: very long straight light purple hair reaching her knees, long white rabbit ears slightly crumpled, red eyes, a white blouse with a red necktie, a black blazer, a short pink skirt, brown loafers.`
  손님 특기: `9. Holding out a small medicine bottle from a medicine box on her back, smiling politely. 10. Pointing her finger like a pistol with a small red sparkle at the fingertip.`

```
python tools/import_sheet.py 메이링A.png meiling --preset move
python tools/import_sheet.py 메이링B.png meiling --preset react
python tools/import_sheet.py 메이링C.png meiling --preset life
python tools/import_sheet.py 메이링걷기.png meiling --preset walk
python tools/import_sheet.py 레이센.png reisen --preset guest
```
