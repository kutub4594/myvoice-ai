class GuidedPrompt {
  const GuidedPrompt({
    required this.id,
    required this.language,
    required this.styleHint,
    required this.text,
  });

  final String id;
  final String language; // 'bn' or 'en'
  final String styleHint;
  final String text;
}

class GuidedPrompts {
  GuidedPrompts._();

  static const List<GuidedPrompt> all = [
    GuidedPrompt(
      id: 'bn_01',
      language: 'bn',
      styleHint: 'Neutral',
      text: 'সকালের রোদে নদীর তীরের বাতাস খুবই স্নিগ্ধ এবং শান্ত মনে হয়।',
    ),
    GuidedPrompt(
      id: 'bn_02',
      language: 'bn',
      styleHint: 'Conversational',
      text: 'আজ বিকেলে তুমি কি একটু সময় করে দেখা করতে পারবে?',
    ),
    GuidedPrompt(
      id: 'bn_03',
      language: 'bn',
      styleHint: 'Expressive',
      text: 'বাহ! এই খবরটা শুনে সত্যিই মনটা আনন্দে ভরে গেল!',
    ),
    GuidedPrompt(
      id: 'bn_04',
      language: 'bn',
      styleHint: 'Calm',
      text: 'রাতের নিস্তব্ধতায় বইয়ের পাতা উল্টে নতুন কিছু শেখার আনন্দই আলাদা।',
    ),
    GuidedPrompt(
      id: 'bn_05',
      language: 'bn',
      styleHint: 'Neutral',
      text: 'শহরের ব্যস্ত রাস্তায় প্রতিদিন হাজারো মানুষ নতুন স্বপ্নের খোঁজে ছুটে চলে।',
    ),
    GuidedPrompt(
      id: 'en_01',
      language: 'en',
      styleHint: 'Neutral',
      text: 'Clear voice recordings in a quiet room help preserve natural vocal tone and rhythm.',
    ),
    GuidedPrompt(
      id: 'en_02',
      language: 'en',
      styleHint: 'Conversational',
      text: 'Hey, let me know once you finish reviewing the audio sample from this morning.',
    ),
    GuidedPrompt(
      id: 'en_03',
      language: 'en',
      styleHint: 'Expressive',
      text: 'That was an incredible result—I could immediately recognize the pacing and warmth!',
    ),
    GuidedPrompt(
      id: 'en_04',
      language: 'en',
      styleHint: 'Calm',
      text: 'Take a steady breath, pause naturally at commas, and read at an easy pace.',
    ),
    GuidedPrompt(
      id: 'en_05',
      language: 'en',
      styleHint: 'Neutral',
      text: 'Technology works best when personal data stays private and under your direct control.',
    ),
  ];
}
