# DS-032 independent unsigned32 bit-vector witness for maintainer review.
# Original repository/base-R evidence only, no live SAS or wide-output claim.
arity <- c(band=2L,bor=2L,bxor=2L,bnot=1L,blshift=2L,brshift=2L)
integer_value <- function(kind,text,shift=FALSE) {
  if(kind!='number') stop('finite integral numeric input required')
  value<-suppressWarnings(as.numeric(text));upper<-if(shift) 31 else 4294967295
  if(length(value)!=1 || !is.finite(value) || value<0 || value>upper || value!=floor(value))
    stop('unsigned32 or shift range')
  value
}
bitwise <- function(name,values) {
  if(!(name %in% names(arity)) || length(values)!=arity[[name]]) stop('exact call arity')
  first<-integer_value(values[[1]]$kind,values[[1]]$text)
  # Expand into explicit low-to-high bits, without signed R bitw primitives.
  bits<-floor(first/2^(0:31)) %% 2
  if(name=='bnot') answer<-1-bits
  else {
    other<-integer_value(values[[2]]$kind,values[[2]]$text,name %in% c('blshift','brshift'))
    if(name %in% c('blshift','brshift')) {
      if(other==0) answer<-bits
      else if(name=='blshift') answer<-c(rep(0,other),head(bits,32-other))
      else answer<-c(tail(bits,32-other),rep(0,other))
    } else {
      more<-floor(other/2^(0:31)) %% 2
      if(name=='band') answer<-bits*more
      else if(name=='bor') answer<-pmin(1,bits+more)
      else answer<-(bits+more) %% 2
    }
  }
  sum(answer*2^(0:31))
}
program <- function(path) {
  source<-paste(readLines(path,warn=FALSE),collapse='\n')
  source<-gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]])
  statements<-statements[nzchar(statements)]
  if(tolower(statements[1])!='data _null_' || tolower(tail(statements,1))!='run') stop('single scalar program required')
  body<-statements[2:(length(statements)-1)]
  parse<-function(text) {
    text<-trimws(text)
    if(grepl('^[+-]?[0-9]+(?:[.][0-9]*)?(?:[eE][+-]?[0-9]+)?$',text,perl=TRUE))
      return(list(kind='number',value=as.numeric(text)))
    if(grepl('^[A-Za-z_][A-Za-z0-9_]*$',text)) return(list(kind='variable',value=tolower(text)))
    m<-regmatches(text,regexec('^([A-Za-z]+)\\((.*)\\)$',text,perl=TRUE))[[1]]
    if(length(m)) {
      name<-tolower(m[2]);pieces<-trimws(strsplit(m[3],',',fixed=TRUE)[[1]])
      if(!(name %in% names(arity)) || length(pieces)!=arity[[name]]) stop('bounded bitwise call required')
      return(list(kind='call',name=name,args=lapply(pieces,parse)))
    }
    stop('expression outside independent program witness')
  }
  order<-character();spelling<-list()
  compiled<-lapply(body,function(statement) {
    if(tolower(statement)=='put _all_') return(list(kind='put'))
    m<-regmatches(statement,regexec('^([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(.*)$',statement,perl=TRUE))[[1]]
    if(!length(m)) stop('statement outside independent program witness')
    key<-tolower(m[2]);if(!(key %in% order)) {order<<-c(order,key);spelling[[key]]<<-m[2]}
    list(kind='assign',target=key,value=parse(m[3]))
  })
  row<-setNames(rep(list(NULL),length(order)),order)
  value<-function(expr) {
    if(expr$kind=='number') return(expr$value)
    if(expr$kind=='variable') {
      if(!(expr$value %in% order) || is.null(row[[expr$value]])) stop('uninitialized witness variable')
      return(row[[expr$value]])
    }
    bitwise(expr$name,lapply(expr$args,function(arg) list(kind='number',text=sprintf('%.17g',value(arg)))))
  }
  records<-0L
  for(op in compiled) {
    if(op$kind=='assign') row[[op$target]]<-value(op$value)
    else {
      pieces<-vapply(order,function(key) {
        x<-row[[key]]
        if(length(x)!=1 || !is.finite(x) || x<0 || x>4294967295 || x!=floor(x)) stop('error-free unsigned32 PDV required')
        paste0(spelling[[key]],'=',sprintf('%.0f',x),' ')
      },'')
      record<-paste0(paste0(pieces,collapse=''),'_ERROR_=0 _N_=1 ')
      width<-nchar(record,type='bytes');records<-records+1L
      # Preserve the DS-025 profile. A wider logical record is refusal evidence.
      if(width>64) {
        cat('WIDTH_REFUSED\t',width,'\t',length(order),'\n',sep='')
        for(key in order) cat('VALUE\t',spelling[[key]],'\t',sprintf('%.0f',row[[key]]),'\n',sep='')
      } else stop('program did not reach expected width boundary')
    }
  }
  if(records!=1L) stop('one width refusal required')
}
args<-commandArgs(trailingOnly=TRUE)
if(length(args)!=2L) stop('usage: bitwise.R cases|program file')
if(args[1]=='program') { program(args[2]) } else if(args[1]=='cases') {
  rows<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  for(i in seq_len(nrow(rows))) {
    answer<-tryCatch({
      count<-as.integer(rows$count[i]);name<-rows$name[i]
      if(!(name %in% names(arity)) || is.na(count) || count!=arity[[name]]) stop('arity')
      values<-list(list(kind=rows$first_kind[i],text=rows$first[i]))
      if(count==2L) values[[2]]<-list(kind=rows$second_kind[i],text=rows$second[i])
      paste0('OK:',sprintf('%.0f',bitwise(name,values)))
    },error=function(e) 'REFUSE')
    cat(rows$id[i],':',answer,'\n',sep='')
  }
} else stop('unknown witness mode')
