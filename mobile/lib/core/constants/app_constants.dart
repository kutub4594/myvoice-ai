class AppConstants {
  AppConstants._();

  static const String appName = 'MyVoice AI';
  static const String defaultBackendUrl = 'https://your-tunnel.trycloudflare.com';
  static const int targetDatasetMinutes = 15;
  static const int maxTextLength = 1000;

  static const List<Map<String, String>> backendPresets = [
    {
      'label': 'Cloudflare / Colab HTTPS Tunnel',
      'url': 'https://your-tunnel.trycloudflare.com',
    },
    {
      'label': 'Android Emulator HTTP Dev (Local Only)',
      'url': 'http://10.0.2.2:8000',
    },
    {
      'label': 'Localhost HTTP Dev (Local Only)',
      'url': 'http://127.0.0.1:8000',
    },
  ];
}
