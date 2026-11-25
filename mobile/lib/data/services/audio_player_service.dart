import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart';
import 'package:myvoice_ai/core/errors/app_exception.dart';

class AudioPlayerService extends ChangeNotifier {
  AudioPlayer? _player;
  String? _activePath;
  bool _isPlaying = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  StreamSubscription<PlayerState>? _stateSub;
  StreamSubscription<Duration>? _posSub;
  StreamSubscription<Duration?>? _durSub;

  AudioPlayer _ensurePlayer() {
    if (_player != null) return _player!;
    final player = AudioPlayer();
    _player = player;
    _stateSub = player.playerStateStream.listen((state) {
      _isPlaying = state.playing && state.processingState != ProcessingState.completed;
      if (state.processingState == ProcessingState.completed) {
        _position = _duration;
      }
      notifyListeners();
    });
    _posSub = player.positionStream.listen((pos) {
      _position = pos;
      notifyListeners();
    });
    _durSub = player.durationStream.listen((dur) {
      _duration = dur ?? Duration.zero;
      notifyListeners();
    });
    return player;
  }

  String? get activePath => _activePath;
  bool get isPlaying => _isPlaying;
  Duration get position => _position;
  Duration get duration => _duration;

  Future<void> togglePlayFile(String filePath) async {
    if (!await File(filePath).exists()) {
      throw const AppException('Audio file could not be found on device.');
    }
    final player = _ensurePlayer();
    if (_activePath == filePath && _isPlaying) {
      await player.pause();
      return;
    }
    if (_activePath != filePath) {
      _activePath = filePath;
      await player.setFilePath(filePath);
    }
    await player.play();
  }

  Future<void> stopIfActive(String filePath) async {
    if (_activePath == filePath) {
      await stop();
    }
  }

  Future<void> stop() async {
    await _player?.stop();
    _activePath = null;
    _position = Duration.zero;
    notifyListeners();
  }

  @override
  void dispose() {
    _stateSub?.cancel();
    _posSub?.cancel();
    _durSub?.cancel();
    _player?.dispose();
    super.dispose();
  }
}
