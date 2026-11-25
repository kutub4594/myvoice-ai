import 'package:flutter/material.dart';
import 'package:myvoice_ai/core/constants/app_constants.dart';
import 'package:myvoice_ai/core/theme/app_theme.dart';
import 'package:myvoice_ai/features/home/home_shell.dart';

class MyVoiceApp extends StatelessWidget {
  const MyVoiceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConstants.appName,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: const HomeShell(),
    );
  }
}
