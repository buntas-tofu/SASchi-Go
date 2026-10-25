# Original DS-031 branch/control witness for maintainer review, no live SAS.
args<-commandArgs(trailingOnly=TRUE)
number<-function(x) if(is.na(x)) '' else sprintf('%.0f',x)
controls<-function(start,stop,step) {
  values<-c(start,stop,step)
  if(any(!is.finite(values)) || any(values!=trunc(values)) || any(abs(values)>2147483647) || step==0) stop('controls')
  count<-if((step>0 && start>stop)||(step<0 && start<stop)) 0 else floor((stop-start)/step)+1
  if(count>10000) stop('trip limit')
  count
}
remainder<-function(x,y) {
  if(!is.finite(y)||y!=trunc(y)||y==0||abs(y)>2^53) stop('bounded MOD')
  x-trunc(x/y)*y
}
if(args[1]=='cases') {
  rows<-read.csv(args[2],stringsAsFactors=FALSE)
  cat('id,status,i,total,branch,seen,after\n')
  for(n in seq_len(nrow(rows))) {
    result<-tryCatch({
      a<-rows$start[n];z<-rows$stop[n];b<-rows$by[n];d1<-rows$first[n];d2<-rows$second[n]
      count<-controls(a,z,b);i<-a;total<-0;branch<-NA_real_;seen<-NA_real_;records<-character()
      for(trip in seq_len(count)) {
        if(remainder(i,d1)==0) branch<-11
        else if(remainder(i,d2)==0) branch<-13
        else branch<-17
        total<-total+branch;seen<-1
        records<-c(records,paste(rows$id[n],'OK',number(i),number(total),number(branch),number(seen),'',sep=','))
        i<-i+b
      }
      c(records,paste(rows$id[n],'OK',number(i),number(total),number(branch),number(seen),number(i),sep=','))
    },error=function(e) paste(rows$id[n],'REFUSE,,,,,',sep=','))
    cat(paste(result,collapse='\n'),'\n',sep='')
  }
} else if(args[1]=='program') {
  source<-paste(readLines(args[2],warn=FALSE),collapse='\n')
  source<-gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  chars<-strsplit(source,'',fixed=TRUE)[[1]];statements<-character();current<-'';quote<-'';i<-1L
  while(i<=length(chars)) {
    char<-chars[i]
    if(quote!='') {
      current<-paste0(current,char)
      if(char==quote) {
        if(i<length(chars)&&chars[i+1]==quote) {i<-i+1L;current<-paste0(current,chars[i])} else quote<-''
      }
    } else if(char %in% c("'",'"')) {quote<-char;current<-paste0(current,char)
    } else if(char==';') {statements<-c(statements,trimws(current));current<-''
    } else current<-paste0(current,char)
    i<-i+1L
  }
  if(quote!=''||trimws(current)!='') stop('unterminated program')
  statements<-statements[nzchar(statements)]
  capture<-function(pattern,text) regmatches(text,regexec(pattern,text,ignore.case=TRUE,perl=TRUE))[[1]]
  if(length(statements)<6 || tolower(statements[1])!='data _null_' ||
     tolower(tail(statements,2)[1])!='end' || tolower(tail(statements,1))!='run') stop('program shape')
  header<-capture('^do\\s+([a-z_][a-z0-9_]*)\\s*=\\s*([+-]?[0-9]+)\\s+to\\s+([+-]?[0-9]+)(?:\\s+by\\s+([+-]?[0-9]+))?$',statements[2])
  if(!length(header)) stop('counted header')
  index<-tolower(header[2]);start<-as.numeric(header[3]);last<-as.numeric(header[4]);step<-if(length(header)<5||!nzchar(header[5])) 1 else as.numeric(header[5])
  count<-controls(start,last,step);divisors<-numeric();labels<-character()
  body<-statements[3:(length(statements)-2)]
  for(k in seq_len(length(body)-1)) {
    prefix<-if(k==1) '^if' else '^else\\s+if'
    pattern<-paste0(prefix,'\\s+mod\\s*\\(\\s*([a-z_][a-z0-9_]*)\\s*,\\s*([+-]?[0-9]+)\\s*\\)\\s*=\\s*0\\s+then\\s+put\\s+(["\x27])(.*)\\3$')
    item<-capture(pattern,body[k]);if(!length(item)||tolower(item[2])!=index) stop('conditional branch')
    divisor<-as.numeric(item[3]);remainder(0,divisor)
    label<-gsub(paste0(item[4],item[4]),item[4],item[5],fixed=TRUE)
    if(nchar(label,type='bytes')>64 || any(utf8ToInt(label)<32|utf8ToInt(label)>126)) stop('literal record')
    divisors<-c(divisors,divisor);labels<-c(labels,label)
  }
  final<-capture('^else\\s+put\\s+([a-z_][a-z0-9_]*)$',tail(body,1))
  if(!length(final)||tolower(final[2])!=index||length(divisors)>32) stop('fallback')
  records<-character();i<-start
  for(trip in seq_len(count)) {
    chosen<-0L
    for(k in seq_along(divisors)) if(remainder(i,divisors[k])==0) {chosen<-k;break}
    record<-if(chosen) labels[chosen] else paste0(number(i),' ')
    records<-c(records,record);i<-i+step
  }
  cat('STATE:',number(i),':',length(records),'\n',sep='')
  for(record in records) cat('RECORD:',paste(sprintf('%02x',as.integer(charToRaw(record))),collapse=''),'\n',sep='')
} else stop('unknown witness mode')
