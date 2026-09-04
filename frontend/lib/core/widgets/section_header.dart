import 'package:flutter/material.dart';
import '../../app/theme/app_typography.dart';
class SectionHeader extends StatelessWidget { final String title; final String? action; final VoidCallback? onAction; const SectionHeader({super.key, required this.title, this.action, this.onAction}); @override Widget build(BuildContext context)=>Row(children:[Text(title,style:AppTypography.section),const Spacer(),if(action!=null)TextButton(onPressed:onAction,child:Text(action!))]); }
