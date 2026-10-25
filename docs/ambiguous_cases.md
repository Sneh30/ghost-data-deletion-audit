# Ambiguous Heuristic Assignments
This report covers the 508 evaluation deletion cases (`case_33`–`case_550`). The 32 public sample cases are excluded from the counts; the one sample fallback (`case_04`) is noted separately because it is the only case that uses a synthetic account id.
## Method
Two non-textual joins are used when the evidence does not name the case directly:
1. **Account mapping.** A request is paired with an `account_service` `DELETE_RECORD` event in a window from 80 minutes before to 15 minutes after the batch `reported_at`. Within a batch, cases are grouped by `reported_status` (matching `SUCCESS`/`PARTIAL`/`FAILED`), ordered by `requested_at` descending with `case_id` ascending, and paired with events ordered by `event_time` ascending. Direct evidence wins first; the synthetic `account_<user-number>` fallback is used only when a complete account snapshot proves absence and the id appears nowhere else.
2. **Anonymous analytics.** Identifier-free analytics rows are attached through `ANONYMIZE_RECORD` activity events. The closest `reported_at` batch within 12 hours is selected. The support/flow/backup block immediately after the last anonymize event names the owner; rows are assigned last-to-first. If there is no block, a single-row batch can use the unique eligible case with no other non-audit/non-analytics resource. Rows with no activity event are used only when exactly one eligible case contains the file in its audit window.
A case is counted as **ambiguous** when more than one event/resource or more than one case was available to the heuristic, or when a fallback method was used. This is a risk indicator, not a claim that the answer is wrong: the deterministic ordering is the tie-breaker.
## Summary
| Heuristic | Cases used | Ambiguous | Fallback |
|---|---:|---:|---:|
| Account — direct fact | 216 | 0 | 0 |
| Account — activity pairing | 282 | 118 | 0 |
| Account — synthetic fallback | 0 | 0 | 0 |
| Anonymous analytics | 92 cases / 155 rows | 87 | 59 |

Unassigned accounts: 10 image-only cases (case_33, case_35, case_39, case_45, case_50, case_52, case_53, case_55, case_61, case_63). They have no account event and no complete snapshot proving a conventional account id.
Analytics methods: block=33, single=51, remainder=8, unique-file=0.
Sample fallback: `case_04` → `account_004`, supported by `evidence_54` and `evidence_90`; the sample gold expects it.
## Ambiguous account mappings
| Case | Source | Chosen | Candidate resources | Candidate cases | Deciding signal | Confidence |
|---|---|---|---|---|---|---|
| case_100 | activity | account_9511 | account_1034, account_7927, account_9511 | case_100, case_98, case_99 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_103 | activity | account_4070 | account_2373, account_4070 | case_103 | reported_status=COMPLETE; batch cases=1; pair requested_at desc with event_time asc | high |
| case_104 | activity | account_8804 | account_4514, account_8804 | case_104, case_106 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_106 | activity | account_4514 | account_4514, account_8804 | case_104, case_106 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_107 | activity | account_687 | account_687, account_7510 | case_107, case_109 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_109 | activity | account_7510 | account_687, account_7510 | case_107, case_109 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_110 | activity | account_7578 | account_2259, account_7578 | case_110, case_112 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_112 | activity | account_2259 | account_2259, account_7578 | case_110, case_112 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_125 | activity | account_7637 | account_6805, account_7637 | case_125, case_127 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_127 | activity | account_6805 | account_6805, account_7637 | case_125, case_127 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_143 | activity | account_2900 | account_2900, account_5572 | case_143, case_145 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_145 | activity | account_5572 | account_2900, account_5572 | case_143, case_145 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_146 | activity | account_5023 | account_5023, account_7864, account_8632 | case_146, case_147, case_148 | reported_status=PARTIALLY_COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_147 | activity | account_8632 | account_5023, account_7864, account_8632 | case_146, case_147, case_148 | reported_status=PARTIALLY_COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_148 | activity | account_7864 | account_5023, account_7864, account_8632 | case_146, case_147, case_148 | reported_status=PARTIALLY_COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_155 | activity | account_1992 | account_1992, account_2154 | case_155, case_157 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_157 | activity | account_2154 | account_1992, account_2154 | case_155, case_157 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_174 | activity | account_246 | account_246, account_6659 | case_174, case_175 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_175 | activity | account_6659 | account_246, account_6659 | case_174, case_175 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_185 | activity | account_9579 | account_3878, account_9579 | case_185, case_186 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_186 | activity | account_3878 | account_3878, account_9579 | case_185, case_186 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_191 | activity | account_6608 | account_6608, account_9317 | case_191, case_192 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_192 | activity | account_9317 | account_6608, account_9317 | case_191, case_192 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_203 | activity | account_2399 | account_2399, account_6726 | case_203, case_205 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_205 | activity | account_6726 | account_2399, account_6726 | case_203, case_205 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_207 | activity | account_5678 | account_3685, account_5678 | case_207, case_208 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_208 | activity | account_3685 | account_3685, account_5678 | case_207, case_208 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_224 | activity | account_7605 | account_392, account_669, account_7605 | case_224, case_225, case_226 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_225 | activity | account_669 | account_392, account_669, account_7605 | case_224, case_225, case_226 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_226 | activity | account_392 | account_392, account_669, account_7605 | case_224, case_225, case_226 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_227 | activity | account_5549 | account_4552, account_5549, account_7146 | case_227, case_228, case_229 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_228 | activity | account_4552 | account_4552, account_5549, account_7146 | case_227, case_228, case_229 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_229 | activity | account_7146 | account_4552, account_5549, account_7146 | case_227, case_228, case_229 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_230 | activity | account_8165 | account_8165, account_8936 | case_230, case_232 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_232 | activity | account_8936 | account_8165, account_8936 | case_230, case_232 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_240 | activity | account_1789 | account_1789, account_6013 | case_240, case_241 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_241 | activity | account_6013 | account_1789, account_6013 | case_240, case_241 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_243 | activity | account_7650 | account_4264, account_7650 | case_243, case_244 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_244 | activity | account_4264 | account_4264, account_7650 | case_243, case_244 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_245 | activity | account_2481 | account_1264, account_2481 | case_245, case_246 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_246 | activity | account_1264 | account_1264, account_2481 | case_245, case_246 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_251 | activity | account_4643 | account_4643, account_7518 | case_251, case_252 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_252 | activity | account_7518 | account_4643, account_7518 | case_251, case_252 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_257 | activity | account_7942 | account_3601, account_7942 | case_257, case_258 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_258 | activity | account_3601 | account_3601, account_7942 | case_257, case_258 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_275 | activity | account_2352 | account_2352, account_731 | case_275, case_277 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_277 | activity | account_731 | account_2352, account_731 | case_275, case_277 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_278 | activity | account_6306 | account_4664, account_6306 | case_278, case_279 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_279 | activity | account_4664 | account_4664, account_6306 | case_278, case_279 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_293 | activity | account_9091 | account_6996, account_8353, account_9091 | case_293, case_294, case_295 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_294 | activity | account_6996 | account_6996, account_8353, account_9091 | case_293, case_294, case_295 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_295 | activity | account_8353 | account_6996, account_8353, account_9091 | case_293, case_294, case_295 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_297 | activity | account_6023 | account_4880, account_6023 | case_297, case_298 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_298 | activity | account_4880 | account_4880, account_6023 | case_297, case_298 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_299 | activity | account_7249 | account_1618, account_7249, account_9993 | case_299, case_300, case_301 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_300 | activity | account_1618 | account_1618, account_7249, account_9993 | case_299, case_300, case_301 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_301 | activity | account_9993 | account_1618, account_7249, account_9993 | case_299, case_300, case_301 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_303 | activity | account_7907 | account_4771, account_7907 | case_303, case_304 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_304 | activity | account_4771 | account_4771, account_7907 | case_303, case_304 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_336 | activity | account_767 | account_2282, account_767 | case_336, case_337 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_337 | activity | account_2282 | account_2282, account_767 | case_336, case_337 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_339 | activity | account_1015 | account_1015, account_1340 | case_339, case_340 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_340 | activity | account_1340 | account_1015, account_1340 | case_339, case_340 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_345 | activity | account_8834 | account_5214, account_8834 | case_345, case_346 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_346 | activity | account_5214 | account_5214, account_8834 | case_345, case_346 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_347 | activity | account_3372 | account_3372, account_9881 | case_347, case_349 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_349 | activity | account_9881 | account_3372, account_9881 | case_347, case_349 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_359 | activity | account_6445 | account_6445, account_7118 | case_359, case_361 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_361 | activity | account_7118 | account_6445, account_7118 | case_359, case_361 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_395 | activity | account_3492 | account_2464, account_3492, account_6443 | case_395, case_396, case_397 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_396 | activity | account_6443 | account_2464, account_3492, account_6443 | case_395, case_396, case_397 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_397 | activity | account_2464 | account_2464, account_3492, account_6443 | case_395, case_396, case_397 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_398 | activity | account_2138 | account_1140, account_2138 | case_398, case_399 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_399 | activity | account_1140 | account_1140, account_2138 | case_398, case_399 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_404 | activity | account_1759 | account_1759, account_8997 | case_404, case_406 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_406 | activity | account_8997 | account_1759, account_8997 | case_404, case_406 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_408 | activity | account_5754 | account_5754, account_7174 | case_408, case_409 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_409 | activity | account_7174 | account_5754, account_7174 | case_408, case_409 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_410 | activity | account_163 | account_163, account_2775, account_8985 | case_410, case_411, case_412 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_411 | activity | account_2775 | account_163, account_2775, account_8985 | case_410, case_411, case_412 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_412 | activity | account_8985 | account_163, account_2775, account_8985 | case_410, case_411, case_412 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_425 | activity | account_1576 | account_1576, account_9633 | case_425, case_426 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_426 | activity | account_9633 | account_1576, account_9633 | case_425, case_426 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_443 | activity | account_4042 | account_1776, account_4042 | case_443, case_444 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_444 | activity | account_1776 | account_1776, account_4042 | case_443, case_444 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_447 | activity | account_7340 | account_6635, account_7340 | case_447, case_448 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_448 | activity | account_6635 | account_6635, account_7340 | case_447, case_448 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_455 | activity | account_6373 | account_2761, account_6373 | case_455, case_457 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_457 | activity | account_2761 | account_2761, account_6373 | case_455, case_457 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_47 | activity | account_617 | account_483, account_617 | case_47, case_48 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_48 | activity | account_483 | account_483, account_617 | case_47, case_48 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_480 | activity | account_9449 | account_2465, account_9449 | case_480, case_481 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_481 | activity | account_2465 | account_2465, account_9449 | case_480, case_481 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_483 | activity | account_9398 | account_2961, account_9398 | case_483, case_484 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_484 | activity | account_2961 | account_2961, account_9398 | case_483, case_484 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_488 | activity | account_1433 | account_1433, account_4036 | case_488, case_490 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_490 | activity | account_4036 | account_1433, account_4036 | case_488, case_490 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_504 | activity | account_8136 | account_7244, account_8136 | case_504, case_505 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_505 | activity | account_7244 | account_7244, account_8136 | case_504, case_505 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_527 | activity | account_3693 | account_3693, account_4063 | case_527, case_529 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_529 | activity | account_4063 | account_3693, account_4063 | case_527, case_529 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_543 | activity | account_8931 | account_7320, account_8931 | case_543, case_544 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_544 | activity | account_7320 | account_7320, account_8931 | case_543, case_544 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_546 | activity | account_294 | account_294, account_8832 | case_546 | reported_status=PARTIALLY_COMPLETE; batch cases=1; pair requested_at desc with event_time asc | high |
| case_547 | activity | account_7015 | account_410, account_7015, account_9155 | case_23, case_547, case_548 | reported_status=NOT_STARTED; batch cases=3; pair requested_at desc with event_time asc | low |
| case_548 | activity | account_9155 | account_410, account_7015, account_9155 | case_23, case_547, case_548 | reported_status=NOT_STARTED; batch cases=3; pair requested_at desc with event_time asc | low |
| case_549 | activity | account_4842 | account_4842, account_7225 | case_549, case_550 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_550 | activity | account_7225 | account_4842, account_7225 | case_549, case_550 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_56 | activity | account_5715 | account_5715, account_9862 | case_56, case_58 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_58 | activity | account_9862 | account_5715, account_9862 | case_56, case_58 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_59 | activity | account_631 | account_5661, account_631 | case_59, case_60 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_60 | activity | account_5661 | account_5661, account_631 | case_59, case_60 | reported_status=COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_74 | activity | account_1495 | account_1495, account_9051 | case_74, case_75 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_75 | activity | account_9051 | account_1495, account_9051 | case_74, case_75 | reported_status=PARTIALLY_COMPLETE; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_95 | activity | account_5815 | account_4176, account_5815 | case_95, case_96 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_96 | activity | account_4176 | account_4176, account_5815 | case_95, case_96 | reported_status=NOT_STARTED; batch cases=2; pair requested_at desc with event_time asc | medium |
| case_98 | activity | account_7927 | account_1034, account_7927, account_9511 | case_100, case_98, case_99 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |
| case_99 | activity | account_1034 | account_1034, account_7927, account_9511 | case_100, case_98, case_99 | reported_status=COMPLETE; batch cases=3; pair requested_at desc with event_time asc | low |

## Ambiguous anonymous-analytics assignments
| Case | Method | Candidate resources | Batch rows | Eligible cases | Following cases | Deciding signal | Confidence |
|---|---|---|---:|---|---|---|---|
| case_103 | single | analytics_3264 | 1 | case_19, case_103 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_110 | remainder | analytics_800 | 2 | case_110, case_111, case_112 | case_112 | remaining eligible case in the intake batch | medium |
| case_112 | block | analytics_9875 | 2 | case_110, case_111, case_112 | case_112 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_113 | single | analytics_4800 | 1 | case_113, case_114 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_117 | single | analytics_8698 | 1 | case_116, case_117, case_118 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_150 | remainder | analytics_7254 | 2 | case_150, case_151 | case_151 | remaining eligible case in the intake batch | medium |
| case_151 | block | analytics_1626 | 2 | case_150, case_151 | case_151 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_155 | block | analytics_8425 | 2 | case_155, case_156, case_157 | case_155, case_172 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_156 | remainder | analytics_7372 | 2 | case_155, case_156, case_157 | case_155, case_172 | remaining eligible case in the intake batch | medium |
| case_164 | single | analytics_6402 | 1 | case_164, case_166 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_170 | single | analytics_6980 | 1 | case_170, case_171, case_172 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_175 | block | analytics_9505 | 1 | case_174, case_175 | case_175 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_178 | single | analytics_2414 | 1 | case_176, case_178 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_190 | single | analytics_8767 | 1 | case_188, case_190 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_193 | single | analytics_8037 | 1 | case_193 | case_208 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_202 | single | analytics_349 | 1 | case_202 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_204 | block | analytics_2463 | 1 | case_203, case_204, case_205 | case_204 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_206 | single | analytics_9580 | 1 | case_206, case_207, case_208 | case_222 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_213 | block | analytics_4460 | 1 | case_213, case_214 | case_213 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_215 | single | analytics_2504 | 1 | case_215, case_217 | case_232 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_231 | block | analytics_1544 | 1 | case_230, case_231, case_232 | case_231 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_233 | block | analytics_6723 | 2 | case_233, case_234, case_235 | case_235, case_233 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_235 | block | analytics_8565 | 2 | case_233, case_234, case_235 | case_235, case_233 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_239 | single | analytics_1964 | 1 | case_239, case_240, case_241 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_253 | single | analytics_6136 | 1 | case_253 | case_268 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_257 | single | analytics_2977 | 1 | case_257, case_258 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_260 | single | analytics_5053 | 1 | case_260 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_264 | block | analytics_1851 | 1 | case_264, case_265 | case_264 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_267 | single | analytics_3793 | 1 | case_266, case_267, case_268 | case_282 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_274 | single | analytics_4051 | 1 | case_274 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_275 | remainder | analytics_5923 | 2 | case_275, case_276, case_277 | case_277 | remaining eligible case in the intake batch | medium |
| case_277 | block | analytics_6191 | 2 | case_275, case_276, case_277 | case_277 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_283 | single | analytics_8408 | 1 | case_283 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_286 | single | analytics_7283 | 1 | case_284, case_286 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_292 | block | analytics_2322 | 1 | case_290, case_291, case_292 | case_292 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_297 | block | analytics_7164 | 1 | case_296, case_297, case_298 | case_297 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_299 | single | analytics_1733 | 1 | case_299, case_300, case_301 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_308 | block | analytics_3678 | 2 | case_308, case_309, case_310 | case_308 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_309 | remainder | analytics_096 | 2 | case_308, case_309, case_310 | case_308 | remaining eligible case in the intake batch | medium |
| case_313 | single | analytics_6099 | 1 | case_313 | case_328 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_314 | single | analytics_5532 | 1 | case_314, case_315, case_316 | case_330 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_319 | single | analytics_2601 | 1 | case_318, case_319 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_322 | single | analytics_4229 | 1 | case_322 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_324 | block | analytics_136 | 1 | case_323, case_324, case_325 | case_324 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_326 | block | analytics_2072 | 2 | case_326, case_327, case_328 | case_326, case_342 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_327 | remainder | analytics_9681 | 2 | case_326, case_327, case_328 | case_326, case_342 | remaining eligible case in the intake batch | medium |
| case_331 | block | analytics_2022 | 1 | case_330, case_331 | case_331 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_335 | block | analytics_3108 | 1 | case_335, case_336, case_337 | case_335, case_352 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_339 | single | analytics_2079 | 1 | case_338, case_339, case_340 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_343 | single | analytics_4751 | 1 | case_343 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_351 | block | analytics_1072 | 1 | case_350, case_351, case_352 | case_351 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_354 | single | analytics_439 | 1 | case_354 | case_370 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_362 | single | analytics_4273 | 1 | case_362 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_369 | single | analytics_2807 | 1 | case_368, case_369 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_378 | single | analytics_3234 | 1 | case_378 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_380 | single | analytics_9326 | 1 | case_380 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_383 | single | analytics_9702 | 1 | case_383, case_384, case_385 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_392 | single | analytics_4328 | 1 | case_392 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_395 | single | analytics_4651 | 1 | case_395, case_396, case_397 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_398 | single | analytics_4455 | 1 | case_398, case_399, case_400 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_403 | single | analytics_7090 | 1 | case_403 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_427 | single | analytics_8091 | 1 | case_426, case_427 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_44 | block | analytics_5589 | 2 | case_03, case_44 | case_44 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_448 | single | analytics_7270 | 1 | case_447, case_448 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_452 | single | analytics_4031 | 1 | case_452 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_458 | single | analytics_5221 | 1 | case_458, case_459, case_460 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_464 | block | analytics_8746 | 1 | case_464, case_466 | case_464 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_470 | single | analytics_4066 | 1 | case_470, case_471, case_472 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_480 | block | analytics_1794 | 1 | case_479, case_480, case_481 | case_480 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_486 | single | analytics_5948 | 1 | case_486 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_493 | single | analytics_5893 | 1 | case_493 | case_508 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_494 | single | analytics_5443 | 1 | case_494, case_495, case_496 | case_510 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_497 | single | analytics_6565 | 1 | case_497, case_498 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_51 | block | analytics_2265 | 1 | case_20, case_51 | case_51 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_512 | single | analytics_1558 | 1 | case_512 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_516 | single | analytics_4804 | 1 | case_515, case_516, case_517 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_521 | single | analytics_7277 | 1 | case_521 | — | unique eligible case with zero non-audit/non-analytics resources | low |
| case_530 | remainder | analytics_3744 | 2 | case_530, case_531, case_532 | case_532 | remaining eligible case in the intake batch | medium |
| case_532 | block | analytics_893 | 2 | case_530, case_531, case_532 | case_532 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_56 | remainder | analytics_2572 | 2 | case_56, case_57, case_58 | case_57 | remaining eligible case in the intake batch | medium |
| case_57 | block | analytics_8858 | 2 | case_56, case_57, case_58 | case_57 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_64 | block | analytics_5718 | 1 | case_09, case_64 | case_64 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_73 | single | analytics_1161 | 1 | case_73 | case_88 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_77 | block | analytics_5859 | 1 | case_77, case_78, case_79 | case_77 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_81 | block | analytics_5059 | 1 | case_80, case_81 | case_81 | anonymize event batch + following support/flow/backup block, assigned last-to-first | medium |
| case_86 | single | analytics_9500 | 1 | case_86, case_87, case_88 | case_102 | unique eligible case with zero non-audit/non-analytics resources | low |
| case_97 | single | analytics_9103 | 1 | case_96, case_97 | — | unique eligible case with zero non-audit/non-analytics resources | low |

## Confidence rubric
- **High:** exactly one candidate, or a block assignment with one row and one eligible case.
- **Medium:** several candidates but a deterministic, evidence-ordered tie-break (status/time, batch block order, remainder).
- **Low:** synthetic account fallback, single-row inference, or unique-file inference; these are the first cases to re-check if the hidden score disagrees.
