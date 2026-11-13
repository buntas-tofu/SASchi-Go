here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'function_wave2_oracles.R'))
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  for(i in seq_len(nrow(cases))) cat(tryCatch(encode(oracle_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c("data cleaned","set raw","normalized=upcase(compbl(strip(label)))","key=cats(substrn(code,1,3),'-',lowcase(tag))","words=countw(normalized,' ')","first=scan(normalized,1,' ')","compact=compress(code,' ')","pos=anydigit(code)","if verify(code,'0123456789 ')=0 then accepted=1","else accepted=0","if missing(label)=1 then blank_label=1","else blank_label=0","output","put key","put accepted","run")
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  if(!identical(names(input),c('label','code','tag'))) stop('input schema')
  rows<-lapply(seq_len(nrow(input)),function(i) list(store(input$label[i],12L),store(input$code[i],6L),store(input$tag[i],3L)))
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(row in rows) emit('raw',row)
  records<-character()
  for(row in rows) {
    label<-row[[1]];code<-row[[2]];tag<-row[[3]]
    normalized<-store(upper_text(ws_call_value('compbl',list(strip_text(label)))),12L)
    key<-store(cat_call_value('cats',list(search_call_value('substrn',list(code,1,3)),'-',lower_text(tag))),200L)
    accepted<-as.numeric(val_call_value('verify',list(code,'0123456789 '))==0)
    blank<-missing_value(label)
    if(TRUE) {
      parts<-word_parts(normalized);words<-length(parts);first<-store(if(length(parts)) parts[1] else '',12L)
      compact<-store(compress_blanks(code),6L);pos<-val_call_value('anydigit',list(code))
      result<-c(row,list(normalized,key,words,first,compact,pos,accepted,blank))
    } else result<-c(row,list(normalized,key,accepted,blank))
    emit('cleaned',result)
    records<-c(records,paste0(strip_text(key),' '),paste0(accepted,' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
