# Expanding a small reference set

If the user has fewer than 15 usable images, build the set up before training.

1. Pick the single best existing image as the anchor.
2. Use it as an img2img / reference input to generate the same character in
   varied poses, angles, expressions, and lighting — WITHOUT changing the
   constant features.
3. Curate down to 20–25 strong, consistent images.
4. Discard any where the constants drifted (wrong hair, lost the signature item).
5. Proceed to captioning.

If the user has NO images (just an idea):
1. Write a tight description of the constants only.
2. Generate a first portrait they love — that's the anchor.
3. Continue from step 2 above.
