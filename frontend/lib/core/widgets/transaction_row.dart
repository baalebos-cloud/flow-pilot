import 'package:flutter/material.dart';
import '../../app/theme/app_colors.dart';
import '../../app/theme/app_spacing.dart';
import '../../core/utils/formatters.dart';
import '../../models/transaction.dart';
import 'status_badge.dart';
class TransactionRow extends StatelessWidget { final Transaction tx; final VoidCallback? onTap; const TransactionRow({super.key,required this.tx,this.onTap}); @override Widget build(BuildContext context){ final incoming=tx.type=='Received'; return ListTile(onTap:onTap,contentPadding:const EdgeInsets.symmetric(horizontal:0,vertical:4),leading:Container(width:42,height:42,decoration:BoxDecoration(color:AppColors.elevated,borderRadius:BorderRadius.circular(12)),child:Icon(incoming?Icons.south_west:Icons.north_east,color:incoming?AppColors.success:AppColors.primaryText,size:19)),title:Text(tx.type,style:const TextStyle(fontWeight:FontWeight.w600)),subtitle:Padding(padding:const EdgeInsets.only(top:4),child:Text(tx.destination,style:const TextStyle(color:AppColors.secondaryText,fontSize:12))),trailing:SizedBox(width:105,child:Column(crossAxisAlignment:CrossAxisAlignment.end,mainAxisAlignment:MainAxisAlignment.center,children:[Text(signedAmount(tx.amount,incoming),style:TextStyle(fontWeight:FontWeight.w600,color:incoming?AppColors.success:AppColors.primaryText)),const SizedBox(height:4),StatusBadge(status:tx.status)]))); } }
