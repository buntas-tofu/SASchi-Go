# Independent full-program numeric and Gregorian calendar calculation.
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
fuzz<-function(x,up) {if(is.na(x)) return(NA_real_);nearest<-round(x);if(abs(x-nearest)<=1e-12) nearest else if(up) ceiling(x) else floor(x)}
date9<-function(d) paste0(format(d,'%d'),c('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')[as.integer(format(d,'%m'))],format(d,'%Y'))
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  invisible(NULL)
  # Scalar groups have their own independent gates.
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data summary','set raw','present=n(amount,backup)','absent=nmiss(amount,backup)','chosen=coalesce(amount,backup)','average=mean(amount,backup)','magnitude=abs(chosen)','direction=sign(chosen)','up=ceil(ratio)','down=floor(ratio)','year=year(d)','month=month(d)','day=day(d)',"months=intck('MONTH',d,ending)","shift=intnx('MONTH',d,move,'S')",'date_text=put(shift,date9.)','value_text=put(average,8.2)','output','put date_text','put value_text','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  rows<-lapply(seq_len(nrow(input)),function(i) lapply(input[i,],function(x) if(nzchar(x)) as.numeric(x) else NA_real_))
  cat('STATEMENTS|',length(statements),'\n',sep='');for(row in rows) emit('raw',row)
  records<-character()
  for(row in rows) {
    values<-unlist(row[1:2]);valid<-values[!is.na(values)];present<-length(valid);chosen<-if(present) valid[1] else NA_real_
    average<-if(present) sum(valid)/present else NA_real_;magnitude<-if(is.na(chosen)) NA_real_ else abs(chosen);direction<-if(is.na(chosen)) NA_real_ else sign(chosen)
    d<-as.Date(row[[4]],origin='1960-01-01');ending<-as.Date(row[[5]],origin='1960-01-01');y<-as.integer(format(d,'%Y'));m<-as.integer(format(d,'%m'));day<-as.integer(format(d,'%d'))
    months<-(as.integer(format(ending,'%Y'))-y)*12L+as.integer(format(ending,'%m'))-m
    target<-y*12L+m-1L+row[[6]];first<-as.Date(sprintf('%04d-%02d-01',target%/%12L,target%%12L+1L));next_index<-target+1L;last<-as.Date(sprintf('%04d-%02d-01',next_index%/%12L,next_index%%12L+1L))-1
    shifted<-first+min(day,as.integer(format(last,'%d')))-1L;shift<-as.numeric(shifted-as.Date('1960-01-01'));date_text<-date9(shifted);value_text<-if(is.na(average)) '       .' else sprintf('%8.2f',average)
    emit('summary',c(row,list(present,2L-present,chosen,average,magnitude,direction,fuzz(row[[3]],TRUE),fuzz(row[[3]],FALSE),y,m,day,months,shift,date_text,value_text)))
    records<-c(records,paste0(date_text,' '),paste0(trimws(value_text,whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
