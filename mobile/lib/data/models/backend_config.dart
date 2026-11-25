import 'package:myvoice_ai/core/constants/app_constants.dart';

class BackendConfig {
  const BackendConfig({
    this.baseUrl = AppConstants.defaultBackendUrl,
    this.uploadConsentRemembered = false,
    this.requestTimeoutSeconds = 90,
  });

  final String baseUrl;
  final bool uploadConsentRemembered;
  final int requestTimeoutSeconds;

  bool get isPlainHttp => baseUrl.trim().toLowerCase().startsWith('http://');

  BackendConfig copyWith({
    String? baseUrl,
    bool? uploadConsentRemembered,
    int? requestTimeoutSeconds,
  }) {
    return BackendConfig(
      baseUrl: baseUrl ?? this.baseUrl,
      uploadConsentRemembered: uploadConsentRemembered ?? this.uploadConsentRemembered,
      requestTimeoutSeconds: requestTimeoutSeconds ?? this.requestTimeoutSeconds,
    );
  }
}
