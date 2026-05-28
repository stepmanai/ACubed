# # engine/evaluation.py

# from acubed.engine.scoring import score_hit


# def evaluate_offsets(offsets, objective):
#     results = []

#     for offset in offsets:
#         judgment, reward = score_hit(offset, objective)

#         results.append(
#             {
#                 "offset": offset,
#                 "judgment": judgment,
#                 "reward": reward,
#             }
#         )

#     return results
