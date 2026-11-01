# Independent whole-source bounded procedure witness, base R only.
# Scanner and generic typed-catalog wire derive from the earlier first-party
# flow witness. Procedure grammar, grouping, sufficient statistics and report
# scheduling below are independently authored; no Python plan is consumed.
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(enc2utf8(x)))),collapse='')
match_parts<-function(pattern,text) {m<-regmatches(text,regexec(paste0('^(?:',pattern,')$'),text,perl=TRUE,ignore.case=TRUE))[[1]];if(length(m)) m[-1] else NULL}
ordinary<-function(n) length(n)==1 && grepl('^[a-z_][a-z0-9_]{0,31}$',n) && !(n %in% c('_n_','_error_','_all_','_numeric_','_character_','_temporary_','_infile_','_file_','_ods_','_page_','_blankpage_','_null_'))
scan_source<-function(path) {
 chars<-strsplit(paste(readLines(path,warn=FALSE),collapse='\n'),'',fixed=TRUE)[[1]];i<-1L;n<-length(chars);buffer<-'';out<-character();lines<-integer();quote<-'';comment<-0L;line<-1L;first<-1L;records<-list()
 while(i<=n) {
  c<-chars[i];nextc<-if(i<n) chars[i+1L] else ''
  if(comment>0L) {if(c=='\n') line<-line+1L;if(c=='/' && nextc=='*') {comment<-comment+1L;i<-i+2L} else if(c=='*' && nextc=='/') {comment<-comment-1L;i<-i+2L;buffer<-paste0(buffer,' ')} else i<-i+1L;next}
  if(nzchar(quote)) {buffer<-paste0(buffer,c);if(c=='\n') line<-line+1L;if(c==quote) {if(nextc==quote) {buffer<-paste0(buffer,nextc);i<-i+1L} else quote<-''};i<-i+1L;next}
  if(c=='/' && nextc=='*') {comment<-1L;i<-i+2L;next}
  if(!nzchar(trimws(buffer)) && (c=='*' || c=='%' && nextc=='*')) {while(i<=n && chars[i]!=';') {if(chars[i]=='\n') line<-line+1L;i<-i+1L};if(i>n) stop('comment terminator');i<-i+1L;next}
  if(!nzchar(trimws(buffer)) && !grepl('[[:space:]]',c)) first<-line
  if(c %in% c("'",'\"')) {quote<-c;buffer<-paste0(buffer,c);i<-i+1L;next}
  if(c==';') {
   text<-trimws(buffer);buffer<-'';i<-i+1L
   if(nzchar(text)) {out<-c(out,text);lines<-c(lines,first)}
   if(tolower(text) %in% c('cards','datalines')) {
    tail<-if(i<=n) paste(chars[i:n],collapse='') else '';physical<-strsplit(paste0(tail,'\nEND'),'\n',fixed=TRUE)[[1]]
    if(nzchar(trimws(physical[1],whitespace=' '))) stop('inline header')
    ending<-which(grepl('^ *; *$',physical));if(!length(ending)) stop('inline terminator');ending<-ending[1]
    records[[as.character(length(out))]]<-if(ending>2L) physical[2:(ending-1L)] else character()
    i<-i+sum(nchar(physical[seq_len(ending)],type='chars'))+ending;line<-line+ending
   }
   next
  }
  if(c=='\n') line<-line+1L
  buffer<-paste0(buffer,if(grepl('[[:space:]]',c)) ' ' else c);i<-i+1L
 }
 if(nzchar(quote) || comment || nzchar(trimws(buffer))) stop('incomplete source')
 list(statements=out,lines=lines,records=records)
}

load_catalog<-function(folder) {
 if(file.exists(file.path(folder,'invalid.flag'))) stop('catalog transport shape')
 tables<-read.csv(file.path(folder,'tables.csv'),colClasses='character',na.strings=NULL);specs<-read.csv(file.path(folder,'descriptors.csv'),colClasses='character',na.strings=NULL);values<-read.csv(file.path(folder,'values.csv'),colClasses='character',na.strings=NULL);result<-list()
 generic_name<-function(n,k) {if(k!='string' || any(as.integer(charToRaw(n))>127) || !grepl('^[A-Za-z_][A-Za-z0-9_]{0,31}$',n)) stop('generic name');tolower(n)}
 for(i in seq_len(nrow(tables))) {
  t<-tables[i,];name<-generic_name(t$table,t$table_kind);if(name %in% names(result)) stop('duplicate table name');keys<-strsplit(t$table_keys,'|',fixed=TRUE)[[1]]
  if(!all(c('schema','rows') %in% keys) || any(!(keys %in% c('schema','rows','encoding','label'))) || !(t$encoding %in% c('-','utf-8','ascii','latin-1')) || !((t$encoding_kind=='-' && t$encoding=='-') || t$encoding_kind=='string') || !(t$dataset_label_kind %in% c('-','string'))) stop('table metadata')
  result[[name]]<-list(schema=list(),rows=replicate(as.integer(t$row_count),list(),simplify=FALSE),encoding=t$encoding,label=t$dataset_label,keys=keys)
 }
 for(i in seq_len(nrow(specs))) {
  d<-specs[i,];table<-tolower(d$table);name<-generic_name(d$name,d$name_kind);if(!(table %in% names(result)) || name %in% names(result[[table]]$schema) || name %in% c('_n_','_error_')) stop('duplicate/reserved schema')
  keys<-if(d$keys=='-') character() else strsplit(d$keys,'|',fixed=TRUE)[[1]]
  if(d$type_kind!='string' || !(d$type %in% c('number','typed-number','character')) || length(keys) && (!('type' %in% keys) || any(!(keys %in% c('type','length','label','format')))) || !(d$label_kind %in% c('-','string')) || !(d$format_kind %in% c('-','string'))) stop('descriptor fields')
  if(d$type %in% c('number','typed-number')) {if(!((d$length=='-' && d$length_kind=='-') || d$length=='8' && d$length_kind=='integer')) stop('numeric width')} else {if(d$length_kind!='integer' || !grepl('^[0-9]+$',d$length) || as.numeric(d$length)<1 || as.numeric(d$length)>32767) stop('character width')}
  result[[table]]$schema[[name]]<-list(type=d$type,length=d$length,label=d$label,format=d$format,keys=keys)
 }
 for(i in seq_len(nrow(values))) {
  v<-values[i,];table<-tolower(v$table);name<-generic_name(v$name,v$name_kind);t<-result[[table]];position<-as.integer(v$row)
  if(is.null(t) || position<1 || position>length(t$rows) || !(name %in% names(t$schema)) || name %in% names(t$rows[[position]])) stop('row name/shape')
  spec<-t$schema[[name]]
  if(v$kind=='missing' && spec$type!='character') x<-NA_real_ else if(v$kind=='number' && spec$type!='character') {x<-as.numeric(v$value);if(!is.finite(x)) stop('finite generic value')} else if(v$kind=='character' && spec$type=='character') {width<-as.integer(spec$length);encoding<-if(t$encoding=='-') 'UTF-8' else if(t$encoding=='latin-1') 'latin1' else t$encoding;encoded<-iconv(v$value,from='UTF-8',to=encoding,sub=NA);if(is.na(encoded)) stop('character encoding');bytes<-nchar(encoded,type='bytes');if(bytes>width) stop('character width');x<-paste0(v$value,strrep(' ',width-bytes))} else if(v$kind=='tagged' && spec$type!='character' && grepl('^[_A-Z]$',v$value)) x<-structure(list(tag=v$value),class='sas_tag') else stop('generic imported type')
  t$rows[[position]][[name]]<-x;result[[table]]<-t
 }
 for(t in result) for(row in t$rows) if(!setequal(names(row),names(t$schema))) stop('generic row shape')
 result
}

# Exact binary digits make the decimal midpoint guard independent of the
# implementation's Fraction arithmetic. M*5^places /2^k is the exact scaled
# binary64 value. Distance to the half-integer must exceed16*5^places units.
midpoint_safe<-function(x,places) {
 exponent<-as.numeric(strsplit(sprintf('%a',abs(x)),'p',fixed=TRUE)[[1]][2])-52
 k<-as.integer(-exponent-places);if(k<=0) return(TRUE)
 value<-abs(x)/(2^exponent);bits<-integer()
 while(value>0) {bits<-c(bits,as.integer(value%%2));value<-floor(value/2)}
 if(places>0) for(j in seq_len(places)) {
  out<-integer(length(bits)+3L);out[seq_along(bits)]<-bits;out[seq_along(bits)+2L]<-out[seq_along(bits)+2L]+bits
  for(i in seq_len(length(out)-1L)) if(out[i]>=2L) {out[i+1L]<-out[i+1L]+out[i]%/%2L;out[i]<-out[i]%%2L}
  bits<-out
 }
 remainder<-integer(k);copied<-min(k,length(bits));if(copied) remainder[seq_len(copied)]<-bits[seq_len(copied)]
 target<-integer(k);target[k]<-1L
 # Work in remainder units: target represents2^(k-1).
 if(remainder[k]) {difference<-remainder;difference[k]<-0L} else {
  difference<-integer(k);borrow<-0L
  for(i in seq_len(k)) {q<-target[i]-remainder[i]-borrow;if(q<0L) {q<-q+2L;borrow<-1L} else borrow<-0L;difference[i]<-q}
 }
 if(length(difference)>29L && any(difference[seq.int(30L,length(difference))])) return(TRUE)
 distance<-sum(difference*2^(seq_along(difference)-1L))
 distance>16*5^places
}
logical_number<-function(x) {
 if(length(x)!=1 || !is.numeric(x) || is.nan(x)) stop('numeric report type')
 if(is.na(x)) return('.')
 if(!is.finite(x) || abs(x)>2147483647 || x!=0 && abs(x)<.Machine$double.xmin) stop('report numeric bounds')
 if(x==0) return('0')
 if(x==trunc(x)) return(sprintf('%.0f',x))
 if(abs(x)<1e-4 || abs(x)>=1e9) stop('report fractional bounds')
 width<-nchar(sprintf('%.0f',trunc(abs(x))));places<-12L-as.integer(x<0)-width-1L
 text<-sprintf(paste0('%.',places,'f'),x)
 if(nchar(text)>12 || !midpoint_safe(x,places)) stop('report width/midpoint')
 text<-sub('0+$','',text);text<-sub('\\.$','',text)
 if(text=='-0') '0' else text
}
number8<-function() list(type='typed-number',length='8',label='-',format='-',keys=c('type','length'))
input_table<-function(tables,name,selected) {
 t<-tables[[name]];if(is.null(t)) stop('missing input table')
 if(length(t$rows)>1000 || any(!(selected %in% names(t$schema)))) stop('row/selected schema bounds')
 for(n in selected) {d<-t$schema[[n]];if(!(d$type %in% c('number','typed-number')) || !(d$format %in% c('-',''))) stop('selected unformatted numeric descriptor')}
 t
}
small_integer<-function(x) {
 if(length(x)!=1 || !is.numeric(x) || is.nan(x)) stop('MEANS numeric type')
 if(is.na(x)) return(NA_real_)
 if(!is.finite(x) || abs(x)>1000 || x!=trunc(x)) stop('MEANS integer magnitude')
 if(x==0) 0 else x
}
source_name<-function(x) {if(any(as.integer(charToRaw(x))>127)) stop('ASCII name');x<-tolower(x);if(!ordinary(x)) stop('ordinary name');x}
name_list<-function(text,max=32) {if(any(as.integer(charToRaw(text))>127)) stop('ASCII names');n<-vapply(strsplit(trimws(text),'[[:space:]]+')[[1]],source_name,'');if(!length(n) || length(n)>max || anyDuplicated(n)) stop('unique name list');unname(n)}
key_parts<-function(x) {
 if(inherits(x,'sas_tag')) return(c(0,if(x$tag=='_') -2 else match(x$tag,LETTERS)-1))
 if(is.na(x)) c(0,-1) else c(1,x)
}
emit_tables<-function(tables) {
 for(name in names(tables)) {
  t<-tables[[name]];cat('TABLE:',name,'\nMETA:',t$encoding,'|',t$label,'\nTABLEKEYS:',paste(t$keys,collapse='|'),'\n',sep='')
  for(n in names(t$schema)) {d<-t$schema[[n]];cat('COLUMN:',paste(c(n,d$type,d$length,d$label,d$format),collapse='|'),'\n',sep='');if(length(d$keys)) cat('COLUMNKEYS:',paste(c(n,d$keys),collapse='|'),'\n',sep='')}
  for(row in t$rows) {cat('ROWKEYS:',paste(names(row),collapse='|'),'\n',sep='');cat('ROW:',paste(vapply(row,function(x) if(inherits(x,'sas_tag')) paste0('T',x$tag) else if(is.character(x)) paste0('C',hex(x)) else if(is.na(x)) 'M' else paste0('N',sprintf('%.17g',x)),''),collapse=','),'\n',sep='')}
 }
}
program<-function(path,folder) {
 scanned<-scan_source(path);s<-scanned$statements;tables<-load_catalog(folder);at<-1L;reports<-list();trace<-character();accounts<-character();prints<-0L
 event<-function(...) trace<<-c(trace,paste(...,sep='|'))
 while(at<=length(s)) {
  start<-at;header<-s[at];if(any(as.integer(charToRaw(header))>127) || nchar(header)>16384) stop('ASCII procedure header')
  end<-at+1L;while(end<=length(s) && tolower(s[end])!='run') {if(grepl('^(?:data|proc)\\s',s[end],perl=TRUE,ignore.case=TRUE)) break;end<-end+1L}
  if(end>length(s) || tolower(s[end])!='run') stop('explicit RUN')
  block<-s[seq.int(at,end)];if(any(nchar(block)>16384) || any(vapply(block,function(x) any(as.integer(charToRaw(x))>127),FALSE))) stop('canonical procedure text')
  at<-end+1L
  m<-match_parts('proc\\s+sort\\s+data\\s*=\\s*([a-z_][a-z0-9_]{0,31})(?:\\s+out\\s*=\\s*([a-z_][a-z0-9_]{0,31}))?(\\s+nodupkey)?',header)
  if(!is.null(m)) {
   if(length(block)!=3L) stop('SORT complete statements');by<-match_parts('by\\s+(.+)',block[2]);if(is.null(by)) stop('SORT BY');keys<-name_list(by[1],64);if(any(keys %in% c('descending','notsorted'))) stop('ascending SORT')
   input<-source_name(m[1]);output<-if(length(m)>1 && nzchar(m[2])) source_name(m[2]) else input;t<-tables[[input]]
   if(is.null(t) || any(!(keys %in% names(t$schema)))) stop('SORT input schema')
   event('sort','input',input,length(t$rows));indices<-seq_along(t$rows)
   for(key in rev(keys)) {
    if(t$schema[[key]]$type=='character') {values<-vapply(t$rows[indices],function(row) row[[key]],'');indices<-indices[order(values,seq_along(values),method='radix')]} else {values<-lapply(t$rows[indices],function(row) key_parts(row[[key]]));a<-vapply(values,function(x) x[1],0.0);b<-vapply(values,function(x) x[2],0.0);indices<-indices[order(a,b,seq_along(a),method='radix')]}
   }
   t$rows<-t$rows[indices];if(length(m)>2 && nzchar(m[3])) {tuples<-lapply(t$rows,function(row) row[keys]);t$rows<-t$rows[!duplicated(tuples)]}
   tables[[output]]<-t;event('sort','output',output,length(t$rows));accounts<-c(accounts,paste('sort',length(indices),length(t$rows),0,0,sep='|'));next
  }
  m<-match_parts('proc\\s+means\\s+data\\s*=\\s*([a-z_][a-z0-9_]{0,31})\\s+noprint\\s+vardef\\s*=\\s*df',header)
  if(!is.null(m)) {
   if(length(block)!=5L) stop('MEANS complete statements');by<-match_parts('by\\s+([a-z_][a-z0-9_]{0,31})',block[2]);var<-match_parts('var\\s+([a-z_][a-z0-9_]{0,31})',block[3]);out<-match_parts('output\\s+out\\s*=\\s*([a-z_][a-z0-9_]{0,31})\\s+(.+)\\s*/\\s*noinherit',block[4]);if(is.null(by) || is.null(var) || is.null(out)) stop('MEANS statements')
   input<-source_name(m[1]);group<-source_name(by[1]);variable<-source_name(var[1]);output<-source_name(out[1]);if(group==variable || group %in% c('_type_','_freq_') || output %in% names(tables)) stop('MEANS names/destination')
   pattern<-'(n|nmiss|mean|var)\\s*=\\s*([a-z_][a-z0-9_]{0,31})';terms<-regmatches(out[2],gregexpr(pattern,out[2],perl=TRUE,ignore.case=TRUE))[[1]]
   if(length(terms)!=4L || nzchar(trimws(gsub(pattern,'',out[2],perl=TRUE,ignore.case=TRUE)))) stop('MEANS aliases full consumption')
   aliases<-lapply(terms,function(term) match_parts(pattern,term));statistics<-tolower(vapply(aliases,function(x) x[1],''));names_out<-vapply(aliases,function(x) source_name(x[2]),'')
   if(!setequal(statistics,c('n','nmiss','mean','var')) || anyDuplicated(names_out) || any(names_out %in% c(group,'_type_','_freq_'))) stop('MEANS aliases unique')
   t<-input_table(tables,input,c(group,variable));groups<-vapply(t$rows,function(row) small_integer(row[[group]]),0.0);values<-vapply(t$rows,function(row) small_integer(row[[variable]]),0.0)
   if(length(groups)>1L) for(i in seq_len(length(groups)-1L)) if((!is.na(groups[i]) && is.na(groups[i+1L])) || !is.na(groups[i]) && !is.na(groups[i+1L]) && groups[i]>groups[i+1L]) stop('MEANS sorted input')
   schema<-list();schema[[group]]<-t$schema[[group]];for(name in c('_type_','_freq_',names_out)) schema[[name]]<-number8();rows<-list();event('means','input',input,length(values));pos<-1L
   while(pos<=length(values)) {
    last<-pos;while(last<length(values) && (is.na(groups[last+1L]) && is.na(groups[pos]) || !is.na(groups[last+1L]) && !is.na(groups[pos]) && groups[last+1L]==groups[pos])) last<-last+1L
    group_values<-values[seq.int(pos,last)];xs<-group_values[!is.na(group_values)];n<-length(xs);total<-0;squares<-0
    for(x in xs) {total<-total+x;squares<-squares+x*x}
    if(abs(total)>1e6 || squares>1e9 || n*squares>1e12 || total*total>1e12) stop('exact sufficient statistics bound')
    stats<-list(n=as.numeric(n),nmiss=as.numeric(length(group_values)-n),mean=if(n) total/n else NA_real_,var=if(n>1) (n*squares-total*total)/(n*(n-1)) else NA_real_)
    row<-list();row[[group]]<-groups[pos];row[['_type_']]<-0;row[['_freq_']]<-as.numeric(length(group_values));for(i in seq_along(names_out)) row[[names_out[i]]]<-stats[[statistics[i]]]
    rows[[length(rows)+1L]]<-row;event('group',if(is.na(groups[pos])) '.' else sprintf('%.0f',groups[pos]),length(group_values),n,length(group_values)-n);pos<-last+1L
   }
   tables[[output]]<-list(schema=schema,rows=rows,encoding='-',label='-',keys=c('schema','rows'));event('means','output',output,length(rows));accounts<-c(accounts,paste('means',length(values),length(rows),length(rows),0,sep='|'));next
  }
  m<-match_parts('proc\\s+print\\s+data\\s*=\\s*([a-z_][a-z0-9_]{0,31})\\s+noobs',header)
  if(!is.null(m)) {
   prints<-prints+1L;if(prints>1L || length(block)!=3L) stop('one complete PRINT')
   var<-match_parts('var\\s+(.+)',block[2]);if(is.null(var)) stop('PRINT VAR');selected<-name_list(var[1]);input<-source_name(m[1]);t<-input_table(tables,input,selected)
   records<-paste(selected,collapse=' ');event('print','input',input,length(t$rows));event('print','header',hex(records))
   for(row in t$rows) {text<-paste(vapply(row[selected],logical_number,''),collapse=' ');records<-c(records,text);event('print','row',hex(text))}
   text<-paste0(paste(records,collapse='\n'),'\n');if(nchar(records[1],type='bytes')>1055 || any(nchar(records[-1],type='bytes')>415) || length(records)>1001 || nchar(text,type='bytes')>417056) stop('PRINT text limits')
   reports[['print.txt']]<-text;event('print','output','print.txt',nchar(text,type='bytes'));accounts<-c(accounts,paste('print',length(t$rows),0,0,length(records),sep='|'));next
  }
  stop('procedure source outside witness grammar')
 }
 cat('STATEMENTS:',length(s),'\n',sep='');emit_tables(tables)
 for(name in names(reports)) cat('REPORT:',name,'|',hex(reports[[name]]),'\n',sep='')
 for(account in accounts) cat('PROCACCOUNT:',account,'\n',sep='')
 for(value in trace) cat('TRACE:',hex(value),'\n',sep='')
}
args<-commandArgs(trailingOnly=TRUE)
if(length(args)==3L && args[1]=='program') program(args[2],args[3]) else if(length(args)==2L && args[1]=='batch') {
 cases<-read.csv(file.path(args[2],'cases.csv'),colClasses='character')
 for(i in seq_len(nrow(cases))) {cat('CASE:',i-1L,'\n',sep='');good<-tryCatch({program(file.path(args[2],cases$source[i]),file.path(args[2],cases$catalog[i]));TRUE},error=function(e) {cat('REASON:',conditionMessage(e),'\n',sep='');FALSE});cat('ANSWER:',if(good) 'OK' else 'REFUSE','\n',sep='')}
} else stop('program source catalog-folder or batch folder')
