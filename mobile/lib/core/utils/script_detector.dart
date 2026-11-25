enum DetectedScript { bengali, english, mixed, empty }

class ScriptSegmentPreview {
  const ScriptSegmentPreview({
    required this.languageCode,
    required this.text,
  });

  final String languageCode; // 'bn' or 'en'
  final String text;
}

class ScriptDetector {
  ScriptDetector._();

  static final RegExp _bengaliRegex = RegExp(r'[\u0980-\u09FF]');
  static final RegExp _latinRegex = RegExp(r'[A-Za-z]');

  static DetectedScript detect(String input) {
    final trimmed = input.trim();
    if (trimmed.isEmpty) return DetectedScript.empty;

    final hasBn = _bengaliRegex.hasMatch(trimmed);
    final hasEn = _latinRegex.hasMatch(trimmed);

    if (hasBn && hasEn) return DetectedScript.mixed;
    if (hasBn) return DetectedScript.bengali;
    return DetectedScript.english;
  }

  static List<ScriptSegmentPreview> previewSegments(String input) {
    final normalized = input.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (normalized.isEmpty) return const [];

    final tokens = normalized.split(' ');
    final groups = <ScriptSegmentPreview>[];
    String? currentLang;
    final currentTokens = <String>[];

    for (final token in tokens) {
      final bnCount = _bengaliRegex.allMatches(token).length;
      final enCount = _latinRegex.allMatches(token).length;
      String? tokenLang;
      if (bnCount > 0 || enCount > 0) {
        tokenLang = bnCount >= enCount ? 'bn' : 'en';
      }

      if (tokenLang == null) {
        if (currentTokens.isNotEmpty) {
          currentTokens.add(token);
        } else {
          currentLang = _bengaliRegex.hasMatch(normalized) ? 'bn' : 'en';
          currentTokens.add(token);
        }
        continue;
      }

      if (currentLang == null) {
        currentLang = tokenLang;
        currentTokens.add(token);
      } else if (currentLang == tokenLang) {
        currentTokens.add(token);
      } else {
        groups.add(ScriptSegmentPreview(
          languageCode: currentLang,
          text: currentTokens.join(' '),
        ));
        currentLang = tokenLang;
        currentTokens
          ..clear()
          ..add(token);
      }
    }

    if (currentTokens.isNotEmpty && currentLang != null) {
      groups.add(ScriptSegmentPreview(
        languageCode: currentLang,
        text: currentTokens.join(' '),
      ));
    }

    return groups;
  }
}
