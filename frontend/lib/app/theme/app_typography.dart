import 'package:flutter/material.dart';
import 'app_colors.dart';

abstract final class AppTypography {
  static const display = TextStyle(fontSize: 36, fontWeight: FontWeight.w700, color: AppColors.primaryText, letterSpacing: -1.2);
  static const amount = TextStyle(fontSize: 30, fontWeight: FontWeight.w700, color: AppColors.primaryText, letterSpacing: -0.8);
  static const title = TextStyle(fontSize: 24, fontWeight: FontWeight.w600, color: AppColors.primaryText);
  static const section = TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.primaryText);
  static const body = TextStyle(fontSize: 15, height: 1.45, color: AppColors.primaryText);
  static const muted = TextStyle(fontSize: 13, height: 1.4, color: AppColors.secondaryText);
}
