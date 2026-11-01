# Independent source scheduler, local labels and exact-decimal statistical oracle.
# Only the independently authored R definition/record decoder is reused.
report_script <- function() {
  for(frame in rev(sys.frames()))if(!is.null(frame$ofile))return(normalizePath(frame$ofile))
  normalizePath(sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1L]))
}
input <- new.env(parent=globalenv())
sys.source(file.path(dirname(report_script()),'formatted_input.R'),envir=input)
# Nested source() in the input witness defines these helpers in its parent.
input$scan_source <- get('scan_source',envir=input,inherits=TRUE)
input$parse_definition <- get('parse_definition',envir=input,inherits=TRUE)
rcheck <- function(value,message='outside bounded informat report witness')if(!isTRUE(value))stop(message)
rjson <- function(value)paste0('"',gsub('"','\\"',gsub('\\','\\\\',value,fixed=TRUE),fixed=TRUE),'"')
rtitle <- function(value,maximum=128L) {
  rcheck(is.character(value) && length(value)==1L && nchar(value,type='bytes')>=1L &&
    nchar(value,type='bytes')<=maximum && ascii(value) && nzchar(trimws(value,whitespace=' ')) && !grepl('[&%]',value));value
}
runquote <- function(value) {
  rcheck(nchar(value)>=2L);q<-substring(value,1L,1L);rcheck(q %in% c("'",'"') && endsWith(value,q))
  inside<-substring(value,2L,nchar(value)-1L);chars<-strsplit(inside,'',fixed=TRUE)[[1L]];out<-'';i<-1L
  while(i<=length(chars)) {
    if(chars[i]==q){rcheck(i<length(chars) && chars[i+1L]==q);i<-i+1L}
    out<-paste0(out,chars[i]);i<-i+1L
  };out
}
# Little-endian base1000 limbs keep every multiplication and carry exact in R.
bn <- function(value) {
  text<-if(is.character(value))value else sprintf('%.0f',value)
  rcheck(length(text)==1L && grepl('^[0-9]+$',text) && nchar(text)<=80L)
  text<-sub('^0+','',text);if(!nzchar(text))return(0)
  result<-numeric();while(nzchar(text)){n<-nchar(text);first<-max(1L,n-2L);result<-c(result,as.numeric(substring(text,first,n)));text<-if(first==1L)'' else substring(text,1L,first-1L)};result
}
btrim <- function(value){while(length(value)>1L && tail(value,1L)==0)value<-head(value,-1L);value}
bmul <- function(a,b) {
  out<-rep(0,length(a)+length(b)+1L)
  for(i in seq_along(a))for(j in seq_along(b)) {
    k<-i+j-1L;carry<-a[i]*b[j]
    while(carry>0){value<-out[k]+carry;out[k]<-value%%1000;carry<-floor(value/1000);k<-k+1L}
  };btrim(out)
}
bcmp <- function(a,b) {
  a<-btrim(a);b<-btrim(b)
  if(length(a)!=length(b))return(sign(length(a)-length(b)))
  for(i in rev(seq_along(a)))if(a[i]!=b[i])return(sign(a[i]-b[i]));0
}
btimes <- function(...)Reduce(bmul,list(...))
rfixed <- function(numerator,denominator,root=FALSE) {
  negative<-startsWith(as.character(numerator),'-');raw<-sub('^-','',as.character(numerator))
  # Numeric R values are converted without scientific spelling before limb use.
  if(!is.character(numerator)){negative<-numerator<0;raw<-sprintf('%.0f',abs(numerator))}
  den<-if(is.character(denominator))denominator else sprintf('%.0f',denominator)
  A<-bn(raw);B<-bn(den);rcheck(any(B!=0) && (!root || !negative))
  if(root) {
    scaled<-btimes(A,bn('10000000000000000'));q<-floor(sqrt(as.numeric(raw)/as.numeric(den))*1e8)
    squared<-function(v)btimes(B,bn(v),bn(v))
    while(bcmp(squared(q),scaled)>0)q<-q-1
    while(bcmp(squared(q+1),scaled)<=0)q<-q+1
    if(bcmp(btimes(bn(4),scaled),squared(2*q+1))>=0)q<-q+1
    negative<-FALSE
  } else {
    scaled<-bmul(A,bn(1e8));q<-floor(as.numeric(raw)/as.numeric(den)*1e8)
    while(bcmp(bmul(B,bn(q)),scaled)>0)q<-q-1
    while(bcmp(bmul(B,bn(q+1)),scaled)<=0)q<-q+1
    if(bcmp(bmul(bn(2),scaled),bmul(B,bn(2*q+1)))>=0)q<-q+1
  }
  value<-paste0(if(negative && q!=0)'-' else '',sprintf('%.0f',floor(q/1e8)),'.',sprintf('%08.0f',q%%1e8))
  rcheck(nchar(value)<=14L);value
}
rgcd <- function(a,b){a<-abs(a);while(b!=0){value<-a%%b;a<-b;b<-value};a}
rratio <- function(a,b){g<-rgcd(a,b);paste0(sprintf('%.0f',a/g),'/',sprintf('%.0f',b/g))}
rstats <- function(values) {
  xs<-as.numeric(unlist(values[!vapply(values,is.null,TRUE)],use.names=FALSE));n<-length(xs)
  rcheck(n<=1000L && all(is.finite(xs)) && all(xs==trunc(xs)) && all(abs(xs)<=1000))
  total<-sum(xs);squares<-sum(xs*xs);pairwise<-0
  if(n>1L)for(j in 2:n)pairwise<-pairwise+sum((xs[j]-xs[seq_len(j-1L)])^2)
  denominator<-n*(n-1L)
  list(n=n,sum=total,squares=squares,mean=if(n)rfixed(total,n)else'.',
       std=if(n>1L)rfixed(pairwise,denominator,TRUE)else'.',
       minimum=if(n)sprintf('%.0f',min(xs))else'.',maximum=if(n)sprintf('%.0f',max(xs))else'.',
       mean_ratio=if(n)rratio(total,n)else'.',variance_ratio=if(n>1L)rratio(pairwise,denominator)else'.')
}
rtable <- function(table,kind,labels=NULL) {
  rcheck(length(table$schema)>=1L && length(table$schema)<=32L && length(table$rows)<=1000L)
  numeric<-character()
  for(name in names(table$schema)) {
    rcheck(ordinary(name));spec<-table$schema[[name]];rcheck(identical(sort(names(spec)),c('length','type')))
    if(spec$type=='number'){rcheck(spec$length==8L);numeric<-c(numeric,name)}
    else rcheck(spec$type=='character' && spec$length>=1L && spec$length<=32L)
  }
  if(kind=='means')rcheck(length(numeric)>=1L && length(numeric)<=8L)
  if(kind=='print')rcheck(length(labels)>=1L && all(names(labels)%in%names(table$schema)))
  for(row in table$rows)for(name in names(table$schema)) {
    value<-row[[name]];spec<-table$schema[[name]]
    if(spec$type=='number')rcheck(is.null(value) || (is.numeric(value) && length(value)==1L && is.finite(value) && value==trunc(value) && abs(value)<=1000))
    else rcheck(is.character(value) && nchar(value,type='bytes')==spec$length && ascii(value))
  };numeric
}
rreport <- function(table,kind,title,labels=NULL) {
  numeric<-rtable(table,kind,labels);trace<-list();append_trace<-function(x)trace[[length(trace)+1L]]<<-x
  header<-if(kind=='means')'variable n mean std min max'else paste(vapply(names(table$schema),function(name)rjson(if(name%in%names(labels))labels[[name]]else name),''),collapse=' ')
  rcheck(nchar(header)<=1055L);records<-character()
  if(!is.null(title)){rtitle(title);records<-c(records,paste0('TITLE: ',title));append_trace(paste0(if(kind=='means')'default-means'else'labelled-print','|title|',hex(tail(records,1L))))}
  records<-c(records,header);prefix<-if(kind=='means')'default-means'else'labelled-print';append_trace(paste0(prefix,'|header|',hex(header)))
  if(kind=='print') {
    for(row in table$rows) {
      values<-vapply(names(table$schema),function(name){value<-row[[name]]
        if(table$schema[[name]]$type=='character')rjson(sub(' +$','',value))else if(is.null(value))'.'else sprintf('%.0f',if(value==0)0 else value)},'')
      record<-paste(values,collapse=' ');rcheck(nchar(record)<=415L);records<-c(records,record);append_trace(paste0(prefix,'|row|',hex(record)))
    }
  } else for(name in numeric) {
    s<-rstats(lapply(table$rows,function(row)row[[name]]));record<-paste(rjson(name),s$n,s$mean,s$std,s$minimum,s$maximum)
    rcheck(nchar(record)<=415L);records<-c(records,record)
    append_trace(paste0(prefix,'|stats|',name,'|',s$n,'|',sprintf('%.0f',s$sum),'|',sprintf('%.0f',s$squares),'|',s$mean_ratio,'|',s$variance_ratio))
    append_trace(paste0(prefix,'|row|',hex(record)))
  }
  text<-paste0(paste(records,collapse='\n'),'\n');rcheck(nchar(text,type='bytes')<=417056L)
  file<-if(kind=='means')'means_01.txt'else'print_01.txt';append_trace(paste0(prefix,'|output|',file,'|',nchar(text,type='bytes')))
  list(file=file,text=text,trace=trace)
}
parse_report_title <- function(text) {
  rcheck(ascii(text));m<-regmatches(text,regexec('^[Tt][Ii][Tt][Ll][Ee](?: +(.+))?$',text,perl=TRUE))[[1L]]
  rcheck(length(m)>=1L);if(length(m)<2L || !nzchar(m[2L]))return(NULL)
  rtitle(runquote(m[2L]))
}
parse_report_labels <- function(text) {
  rcheck(ascii(text) && grepl('^[Ll][Aa][Bb][Ee][Ll] +',text));rest<-sub('^[Ll][Aa][Bb][Ee][Ll] +','',text);result<-list()
  while(nzchar(rest)) {
    m<-regmatches(rest,regexec("^ *([A-Za-z_][A-Za-z0-9_]{0,31}) *= *(\"(?:[^\"]|\"\")*\"|'(?:[^']|'')*')( |$)",rest,perl=TRUE))[[1L]]
    rcheck(length(m)>=3L && length(result)<32L);name<-tolower(m[2L]);rcheck(ordinary(name) && !name%in%names(result))
    result[[name]]<-rtitle(runquote(m[3L]),64L);rest<-substring(rest,nchar(m[1L])+1L)
  };rcheck(length(result)>=1L);result
}
execute_reports <- function(source) {
  st<-input$scan_source(source);at<-1L;registry<-list();tables<-list();reports<-list();title<-NULL;trace<-list()
  totals<-c(statements=length(st),definitions=0L,producers=0L,physical_records=0L,attempts=0L,observations=0L,outputs=0L,titles=0L,prints=0L,means=0L,printed_rows=0L,analysis_variables=0L);steps<-0L
  while(at<=length(st)) {
    text<-tolower(st[[at]]$text);steps<-steps+1L;rcheck(steps<=64L)
    if(text=='proc format') {
      rcheck(at+2L<=length(st) && length(registry)<8L);definition<-input$parse_definition(st[at+0:2]);rcheck(!definition$name%in%names(registry))
      registry[[definition$name]]<-definition;totals['definitions']<-totals['definitions']+1L;at<-at+3L
    } else if(grepl('^data ',text)) {
      rcheck(at+3L<=length(st) && totals['producers']<8L);data<-input$execute_data_block(st[at+0:3],registry);rcheck(!data$name%in%names(tables))
      tables[[data$name]]<-data$table;trace<-c(trace,data$trace);totals[names(data$accounting)]<-totals[names(data$accounting)]+data$accounting;at<-at+4L
    } else if(grepl('^title( |$)',text)) {
      title<-parse_report_title(st[[at]]$text);totals['titles']<-totals['titles']+1L;rcheck(totals['titles']<=32L)
      trace[[length(trace)+1L]]<-if(is.null(title))'informat-title|reset'else paste0('informat-title|set|',hex(title));at<-at+1L
    } else {
      rcheck(ascii(st[[at]]$text));m<-regmatches(text,regexec('^proc (print|means) data *= *([a-z_][a-z0-9_]{0,31})( label noobs)?$',text))[[1L]]
      rcheck(length(m)>=3L && ordinary(m[3L]) && m[3L]%in%names(tables));kind<-m[2L];name<-m[3L];table<-tables[[name]]
      if(kind=='print') {
        rcheck(length(m)>=4L && m[4L]==' label noobs' && at+2L<=length(st) && tolower(st[[at+2L]]$text)=='run')
        labels<-parse_report_labels(st[[at+1L]]$text);totals['prints']<-totals['prints']+1L;rcheck(totals['prints']<=1L)
        totals['printed_rows']<-totals['printed_rows']+length(table$rows);at<-at+3L
      } else {
        rcheck((length(m)<4L || !nzchar(m[4L])) && at+1L<=length(st) && tolower(st[[at+1L]]$text)=='run')
        labels<-NULL;totals['means']<-totals['means']+1L;rcheck(totals['means']<=1L)
        totals['analysis_variables']<-totals['analysis_variables']+length(rtable(table,'means'));at<-at+2L
      }
      report<-rreport(table,kind,title,labels);rcheck(!report$file%in%names(reports));reports[[report$file]]<-report$text
      trace[[length(trace)+1L]]<-paste0(if(kind=='means')'default-means'else'labelled-print','|input|',name,'|',length(table$rows));trace<-c(trace,report$trace)
    }
  }
  rcheck(length(registry)>=1L && totals['producers']>=1L)
  list(tables=tables,reports=reports,trace=trace,accounting=c(totals,steps=steps))
}
render_reports <- function(result) {
  for(name in names(result$tables)) {
    table<-result$tables[[name]];cat('TABLE ',name,'\n',sep='')
    for(column in names(table$schema)){spec<-table$schema[[column]];cat('COL ',column,' ',spec$type,' ',spec$length,'\n',sep='')}
    for(row in table$rows)cat('ROW ',paste(vapply(names(table$schema),function(column){value<-row[[column]]
      if(table$schema[[column]]$type=='character')paste0('C:',hex(value))else if(is.null(value))'M'else paste0('N:',sprintf('%.0f',value))},''),collapse='|'),'\n',sep='')
    cat('ENDTABLE\n')
  }
  for(name in names(result$reports))cat('REPORT ',name,' ',hex(result$reports[[name]]),'\n',sep='')
  for(event in result$trace) {
    if(is.character(event))cat('TRACE_STRING ',hex(event),'\n',sep='')
    else if(event$kind=='formatted_input')cat('TRACE_INPUT ',event$line,' ',event$attempt,' ',as.integer(event$complete),'\n',sep='')
    else cat('TRACE_OUTPUT ',event$line,' ',event$observation,'\n',sep='')
  }
  cat('ACCOUNT ',paste(result$accounting,collapse=' '),'\n',sep='')
}
report_main <- function() {
  args<-commandArgs(trailingOnly=TRUE);rcheck(length(args)==1L)
  paths<-readLines(args[1L],warn=FALSE)
  for(i in seq_along(paths)) {
    cat('BEGIN ',i,'\n',sep='')
    tryCatch({source<-paste(readLines(paths[i],warn=FALSE),collapse='\n');result<-execute_reports(source);render_reports(result);cat('OK\n')},error=function(e)cat('REFUSED\n'))
    cat('END\n')
  }
}
if(sys.nframe()==0L)report_main()
