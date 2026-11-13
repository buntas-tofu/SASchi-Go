here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'function_wave3_oracles.R'))
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(oracle_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 source<-paste(readLines(args[2],warn=FALSE),collapse='\n');statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
 required<-c("data records","set raw","proper=propcase(label,' -')","wrapped=quote(code)","bare=dequote(code)","marks=countc(label,'-')","cleaned=transtrn(label,'-',trimn(' '))","identifier=cats(propcase(label,' -'),'-',dequote(code))","upperpos=anyupper(code)","lowerpos=anylower(code)","badpos=notalnum(code)","look=whichc(bare,'A','B','A')","rank=whichn(flag,0,1,1)","picked=choosec(index,'FIRST','SECOND','THIRD')","amount=choosen(index,a,b,c)","decision=ifc(notalnum(code)=0,'OK','REVIEW')","chosen=ifn(flag,fallback,largest(k,a,b,c))","if anyupper(code)>0 then has_upper=1","else has_upper=0","if missing(label)=1 then blank=1","else blank=0","output","put identifier","put decision","put chosen","run")
 if(!identical(statements,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 if(!identical(names(input),c('label','code','flag','a','b','c','k','fallback','index'))) stop('schema')
 rows<-lapply(seq_len(nrow(input)),function(i) c(list(store(input$label[i],12L),store(input$code[i],8L)),lapply(input[i,3:9],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)))
 cat('STATEMENTS|',length(statements),'\n',sep='');records<-character()
 for(row in rows) emit('raw',row)
 for(row in rows) {
  label<-row[[1]];code<-row[[2]];flag<-row[[3]];values<-row[4:6];k<-row[[7]];fallback<-row[[8]];index<-row[[9]]
  status<-sel_call_value('ifc',list(as.numeric(pos_call_value('notalnum',list(code))==0),'OK','REVIEW'))
  ranked<-rank_call_value('largest',c(list(k),values))
  chosen<-sel_call_value('ifn',list(flag,fallback,ranked))
  proper<-txt_call_value('propcase',list(label,' -'));bare<-txt_call_value('dequote',list(code))
  identifier<-paste0(sub(' +$','',sub('^ +','',proper)),'-',sub(' +$','',sub('^ +','',bare)))
  # Exact deletion is intentionally distinct from the stored single blank.
  cleaned<-txt_call_value('transtrn',list(label,'-',''));blanked<-txt_call_value('transtrn',list(label,'-',' '))
  has_upper<-as.numeric(pos_call_value('anyupper',list(code))>0)
  if(TRUE) {
   wrapped<-txt_call_value('quote',list(code));marks<-txt_call_value('countc',list(label,'-'))
   positions<-lapply(c('anyupper','anylower','notalnum'),function(name) pos_call_value(name,list(code)))
   look<-sel_call_value('whichc',list(store(bare,8L),'A','B','A'));rank<-sel_call_value('whichn',list(flag,0,1,1))
   picked<-sel_call_value('choosec',list(index,'FIRST','SECOND','THIRD'));amount<-sel_call_value('choosen',c(list(index),values))
   blank<-as.numeric(!nzchar(sub(' +$','',label)))
   result<-c(row,list(store(proper,12L),store(wrapped,200L),store(bare,8L),marks,store(cleaned,200L),store(identifier,200L)),positions,list(look,rank,store(picked,200L),amount,store(status,200L),chosen,has_upper,blank))
   records<-c(records,paste0(identifier,' '),paste0(status,' '),paste0(if(is.na(chosen)) '.' else sprintf('%.17g',chosen),' '))
  } else {
   result<-c(row,list(store(status,200L),chosen,store(identifier,200L),store(cleaned,200L),store(blanked,200L),has_upper))
   records<-c(records,paste0(identifier,' '),paste0(if(is.na(chosen)) '.' else sprintf('%.17g',chosen),' '))
  }
  emit('records',result)
 }
 for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
