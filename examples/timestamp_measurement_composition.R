here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'function_wave2_oracles.R'))
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  for(i in seq_len(nrow(cases))) cat(tryCatch(encode(oracle_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c("data reconciled","set raw","quarter=qtr(day)","stamp=dhms(day,hr,mn,sc)","recovered=datepart(stamp)","clock=timepart(stamp)","h=hour(stamp)","m=minute(stamp)","s=second(stamp)","yr=year(recovered)","mo=month(recovered)","dy=day(recovered)","mid=median(a,b,c)","spread=range(a,b,c)","variance=var(a,b,c)","deviation=std(a,b,c)","average=mean(a,b,c)","magnitude=abs(average)","period=intnx('MONTH',recovered,0,'B')","months=intck('MONTH',0,recovered)","if missing(a)=1 then absent=1","else absent=0","shown=put(recovered,date9.)","output","put shown","put absent","run")
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  if(!identical(names(input),c('id','day','hr','mn','sc','a','b','c'))) stop('input schema')
  number<-function(x) if(!nzchar(x)) NA_real_ else as.numeric(x)
  rows<-lapply(seq_len(nrow(input)),function(i) c(list(store(input$id[i],3L)),lapply(input[i,-1L],number)))
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(row in rows) emit('raw',row)
  records<-character()
  for(row in rows) {
    quarter<-dt_call_value('qtr',row[2]);stamp<-dt_call_value('dhms',row[2:5])
    components<-lapply(c('datepart','timepart','hour','minute','second'),function(name) dt_call_value(name,list(stamp)))
    recovered<-components[[1]]
    civil<-lapply(c('%Y','%m','%d'),function(part) calendar_part(recovered,part))
    values<-row[6:8];statistics<-lapply(c('median','range','var','std'),function(name) stats_call_value(name,values))
    average<-old_mean(values);magnitude<-if(is.na(average)) NA_real_ else abs(average)
    period<-month_begin(recovered);months<-month_distance(recovered);absent<-missing_value(row[[6]])
    shown<-dt_date9(recovered)
    emit('reconciled',c(row,list(quarter,stamp),components,civil,statistics,list(average,magnitude,period,months,absent,shown)))
    records<-c(records,paste0(strip_text(shown),' '),paste0(absent,' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
