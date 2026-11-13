here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'function_wave2_oracles.R'))
source(file.path(here,'function_wave3_oracles.R'))
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(oracle_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 source<-paste(readLines(args[2],warn=FALSE),collapse='\n');statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
 required<-c("data quarters","set raw","clock=hms(hr,mn,sc)","quarterdate=yyq(yr,q)","observed=datejul(ordinal)","back=juldate7(observed)","quarterback=juldate7(quarterdate)","year=year(observed)","month=month(observed)","day=day(observed)","quarter=qtr(observed)","stamp=dhms(observed,hr,mn,sc)","recovered=datepart(stamp)","time=timepart(stamp)","present=n(a,b,c)","absent=nmiss(a,b,c)","high=largest(k,a,b,c)","low=smallest(k,a,b,c)","centered=css(a,b,c)","uncentered=uss(a,b,c)","chosen=ifn(flag,fallback,largest(k,a,b,c))","raised=ceilz(value)","lowered=floorz(value)","integral=intz(value)","rounded=roundz(value,unit)","remainder=modz(value,divisor)","if missing(a)=1 then a_missing=1","else a_missing=0","shown=put(observed,date9.)","output","put shown","put time","put chosen","run")
 if(!identical(statements,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 if(!identical(names(input),c('id','yr','q','ordinal','hr','mn','sc','a','b','c','k','flag','fallback','value','unit','divisor'))) stop('schema')
 rows<-lapply(seq_len(nrow(input)),function(i) c(list(store(input$id[i],4L)),lapply(input[i,2:16],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)))
 cat('STATEMENTS|',length(statements),'\n',sep='');records<-character()
 for(row in rows) emit('raw',row)
 for(row in rows) {
  clock<-cal_call_value('hms',row[5:7]);quarterdate<-cal_call_value('yyq',row[2:3]);observed<-cal_call_value('datejul',row[4])
  back<-cal_call_value('juldate7',list(observed));quarterback<-cal_call_value('juldate7',list(quarterdate))
  civil<-lapply(c('%Y','%m','%d'),function(part) calendar_part(observed,part));quarter<-dt_call_value('qtr',list(observed))
  stamp<-dt_call_value('dhms',c(list(observed),row[5:7]));recovered<-dt_call_value('datepart',list(stamp));time<-dt_call_value('timepart',list(stamp))
  values<-row[8:10];present<-sum(!is.na(unlist(values)));absent<-3L-present;k<-row[[11]]
  high<-rank_call_value('largest',c(list(k),values));low<-rank_call_value('smallest',c(list(k),values))
  centered<-rank_call_value('css',values);uncentered<-rank_call_value('uss',values)
  chosen<-sel_call_value('ifn',list(row[[12]],row[[13]],rank_call_value('largest',c(list(k),values))))
  value<-row[[14]];unit<-row[[15]];divisor<-row[[16]]
  integers<-lapply(c('ceilz','floorz','intz'),function(name) zero_call_value(name,list(value)))
  rounded<-zero_call_value('roundz',list(value,unit));remainder<-zero_call_value('modz',list(value,divisor));a_missing<-as.numeric(is.na(row[[8]]));shown<-dt_date9(observed)
  emit('quarters',c(row,list(clock,quarterdate,observed,back,quarterback),civil,list(quarter,stamp,recovered,time,present,absent,high,low,centered,uncentered,chosen),integers,list(rounded,remainder,a_missing,shown)))
  records<-c(records,paste0(trimws(shown,whitespace=' '),' '),paste0(if(is.na(time)) '.' else sprintf('%.17g',time),' '),paste0(if(is.na(chosen)) '.' else sprintf('%.17g',chosen),' '))
 }
 for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
