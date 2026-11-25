import 'package:flutter_test/flutter_test.dart';
import 'package:myvoice_ai/core/utils/script_detector.dart';

void main() {
  group('ScriptDetector', () {
    test('detects Bengali, English, mixed, and empty strings', () {
      expect(ScriptDetector.detect(''), DetectedScript.empty);
      expect(ScriptDetector.detect('আমি বাংলায় কথা বলি'), DetectedScript.bengali);
      expect(ScriptDetector.detect('Hello MyVoice AI'), DetectedScript.english);
      expect(ScriptDetector.detect('আজকে আমি office যাচ্ছি'), DetectedScript.mixed);
    });

    test('segments mixed Bengali and English text sequentially', () {
      final segments = ScriptDetector.previewSegments('আমি Flutter এবং Python ব্যবহার করি।');
      expect(segments.length, 4);
      expect(segments[0].languageCode, 'bn');
      expect(segments[1].languageCode, 'en');
      expect(segments[2].languageCode, 'bn');
      expect(segments[3].languageCode, 'en');
    });
  });
}
