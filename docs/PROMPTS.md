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
