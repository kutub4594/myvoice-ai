import 'dart:io';

import 'package:myvoice_ai/core/errors/app_exception.dart';
import 'package:share_plus/share_plus.dart';

class ExportService {
  Future<void> shareOrSaveAudio({
    required String filePath,
    required String format,
    required String label,
  }) async {
    final file = File(filePath);
    if (!await file.exists()) {
      throw const AppException('Audio file no longer exists on device.');
    }
    final mime = format.toLowerCase() == 'mp3' ? 'audio/mpeg' : 'audio/wav';
    await SharePlus.instance.share(
      ShareParams(
        files: [XFile(filePath, mimeType: mime)],
        subject: 'MyVoice AI ($label.$format)',
      ),
    );
  }
}
