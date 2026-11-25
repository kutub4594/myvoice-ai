import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:myvoice_ai/core/errors/app_exception.dart';
import 'package:myvoice_ai/data/models/backend_config.dart';
import 'package:myvoice_ai/data/models/backend_health.dart';
import 'package:myvoice_ai/data/models/voice_profile.dart';
import 'package:path/path.dart' as p;

class SynthesisResultBytes {
  const SynthesisResultBytes({
    required this.bytes,
    required this.engineId,
    required this.isMock,
    required this.segmentCount,
  });

  final Uint8List bytes;
  final String engineId;
  final bool isMock;
  final int segmentCount;
}

class ApiClientService {
  Dio _buildClient(BackendConfig config) {
    final normalizedUrl = config.baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(normalizedUrl);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      throw const AppException('Invalid backend URL. Enter a valid http:// or https:// address.');
    }
    return Dio(
      BaseOptions(
        baseUrl: normalizedUrl,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: Duration(seconds: config.requestTimeoutSeconds),
        sendTimeout: const Duration(seconds: 45),
      ),
    );
  }

  Future<BackendHealth> checkHealth(BackendConfig config) async {
    try {
      final resp = await _buildClient(config).get<Map<String, dynamic>>('/health');
      if (resp.data == null) {
        throw const AppException('Empty health response from backend.');
      }
      return BackendHealth.fromJson(resp.data!);
    } on DioException catch (e) {
      throw AppException(_formatDioError(e));
    }
  }

  Future<SynthesisResultBytes> synthesize({
    required BackendConfig config,
    required VoiceProfile profile,
    required SpeakingStyle style,
    required String text,
    required String languageMode,
    required String outputFormat,
    required double speed,
    required double exaggeration,
    required double cfgWeight,
    required int pauseMs,
    required bool consentConfirmed,
  }) async {
    if (!consentConfirmed) {
      throw const AppException('Explicit upload consent is required before sending voice samples.');
    }

    final clip = profile.clipForStyle(style);
    if (profile.profileType == ProfileType.zeroShot && clip == null) {
      throw const AppException('Selected profile has no recorded or uploaded voice sample.');
    }

    try {
      final formMap = <String, dynamic>{
        'text': text,
        'language_mode': languageMode,
        'output_format': outputFormat,
        'profile_type': profile.profileType.apiValue,
        'style': style.apiValue,
        'speed': speed.toStringAsFixed(2),
        'exaggeration': exaggeration.toStringAsFixed(2),
        'cfg_weight': cfgWeight.toStringAsFixed(2),
        'pause_ms': pauseMs.toString(),
        'consent_confirmed': 'true',
      };

      if (profile.trainedCheckpointId != null && profile.trainedCheckpointId!.isNotEmpty) {
        formMap['trained_checkpoint_id'] = profile.trainedCheckpointId;
      }
      if (clip != null) {
        if (!await File(clip.filePath).exists()) {
          throw const AppException(
            'Reference voice sample file is missing from device storage. Re-record or re-upload it.',
          );
        }
        if (clip.transcript != null && clip.transcript!.trim().isNotEmpty) {
          formMap['reference_text'] = clip.transcript!.trim();
        }
        formMap['reference_audio'] = await MultipartFile.fromFile(
          clip.filePath,
          filename: p.basename(clip.filePath),
        );
      }

      final resp = await _buildClient(config).post<List<int>>(
        '/api/v1/synthesize',
        data: FormData.fromMap(formMap),
        options: Options(responseType: ResponseType.bytes),
      );

      final bytes = Uint8List.fromList(resp.data ?? const []);
      if (bytes.isEmpty) {
        throw const AppException('Backend returned empty audio data.');
      }

      return SynthesisResultBytes(
        bytes: bytes,
        engineId: resp.headers.value('x-voice-engine') ?? 'unknown',
        isMock: resp.headers.value('x-engine-is-mock') == 'true',
        segmentCount: int.tryParse(resp.headers.value('x-segment-count') ?? '') ?? 1,
      );
    } on DioException catch (e) {
      throw AppException(_formatDioError(e));
    } on FileSystemException catch (e) {
      throw AppException('Failed to read local voice sample: ${e.message}');
    }
  }

  String _formatDioError(DioException e) {
    final data = e.response?.data;
    if (data is Map<String, dynamic> && data['detail'] != null) {
      return data['detail'].toString();
    }
    if (data is List<int>) {
      final text = String.fromCharCodes(data);
      if (text.isNotEmpty) return text;
    }
    return e.message ?? 'Network error while communicating with backend.';
  }
}
