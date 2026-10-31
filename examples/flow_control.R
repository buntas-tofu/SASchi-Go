# Independent staged scalar-flow full-source interpreter; base R only.
# Independent DS-060/061 complete-source integer state and event witness.
limit<-2147483647
integer_value<-function(x) {
  if(length(x)!=1L || !is.numeric(x) || is.nan(x)) stop('numeric type')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || abs(x)>limit || x!=trunc(x)) stop('integer value bound')
  if(x==0) 0 else x
}
ordinary<-function(n) grepl('^[a-z_][a-z0-9_]{0,31}$',n) && !(n %in% c('_n_','_error_','_all_','_numeric_','_character_','_temporary_','_infile_','_file_','_ods_','_page_','_blankpage_','_null_'))
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(enc2utf8(x)))),collapse='')
show<-function(x) if(is.na(x)) '.' else sprintf('%.0f',x)
match_parts<-function(pattern,text) {m<-regmatches(text,regexec(paste0('^(?:',pattern,')$'),text,perl=TRUE,ignore.case=TRUE))[[1]];if(length(m)) m[-1] else NULL}
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

expression<-function(text,control=FALSE) {
 if(any(as.integer(charToRaw(text))>127) || nchar(text)>4096) stop('ASCII expression')
 pattern<-'[0-9]+(?:\\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\\.[0-9]+(?:[eE][+-]?[0-9]+)?|[A-Za-z_][A-Za-z0-9_]*|[.(),+*-]'
 if(control) pattern<-'[0-9]+|[A-Za-z_][A-Za-z0-9_]*|[()+-]'
 locations<-gregexpr(pattern,text,perl=TRUE);tokens<-regmatches(text,locations)[[1]];positions<-as.integer(locations[[1]])
 if(control && length(tokens)>128) stop('control token budget')
 if(!length(tokens) || paste(tokens,collapse='')!=gsub('[[:space:]]','',text)) stop('expression tokens')
 at<-1L;peek<-function() if(at<=length(tokens)) tokens[at] else ''
 take<-function() {if(at>length(tokens)) stop('expression end');x<-tokens[at];at<<-at+1L;x}
 atom<-function(depth) {
  if(depth>32) stop('expression depth');x<-take()
  if(x=='(') {v<-addition(depth+1L);if(take()!=')') stop('parenthesis');return(v)}
  if(x %in% c('+','-')) {
   sign_position<-at-1L;literal<-at<=length(tokens) && grepl('^(?:[0-9]|\\.[0-9])',peek(),perl=TRUE) && positions[at]==positions[sign_position]+1L
   v<-atom(depth+1L)
   if(literal && v$kind=='number') return(list(kind='number',value=integer_value(if(x=='-') -v$value else v$value)))
   return(if(x=='+') v else list(kind='arithmetic',op='-',left=list(kind='number',value=0),right=v))
  }
  if(x=='.') return(list(kind='number',value=NA_real_))
  if(grepl('^[0-9.]',x)) return(list(kind='number',value=integer_value(as.numeric(x))))
  name<-tolower(x)
  if(peek()=='(') {if(control || name!='mod') stop('function');take();a<-addition(depth+1L);if(take()!=',') stop('MOD separator');b<-addition(depth+1L);if(take()!=')') stop('MOD close');return(list(kind='call',args=list(a,b)))}
  if(!(ordinary(name) || name=='_n_')) stop('operand name')
  list(kind='variable',name=name)
 }
 product<-function(depth) {v<-atom(depth);while(peek()=='*') {take();v<-list(kind='arithmetic',op='*',left=v,right=atom(depth+1L))};v}
 addition<-function(depth) {v<-product(depth);while(peek() %in% c('+','-')) {op<-take();v<-list(kind='arithmetic',op=op,left=v,right=product(depth+1L))};v}
 value<-addition(1L);if(at<=length(tokens)) stop('unconsumed expression');value
}
static<-function(e,control=FALSE,depth=1L) {
 if(depth>32) stop('expression depth')
 if(e$kind=='number') {if(control && is.na(e$value)) stop('missing control');return(list(known=TRUE,value=e$value))}
 if(e$kind=='variable') return(list(known=FALSE))
 if(e$kind=='call') {if(control) stop('control call');a<-static(e$args[[1]],FALSE,depth+1L);b<-static(e$args[[2]],FALSE,depth+1L);if(a$known && is.na(a$value) || b$known && (is.na(b$value) || b$value==0)) stop('MOD constant domain');if(!a$known || !b$known) return(list(known=FALSE));return(list(known=TRUE,value=integer_value(a$value-trunc(a$value/b$value)*b$value)))}
 if(control && e$op=='*') stop('control arithmetic')
 a<-static(e$left,control,depth+1L);b<-static(e$right,control,depth+1L)
 if(!a$known || !b$known) return(list(known=FALSE))
 value<-if(is.na(a$value) || is.na(b$value)) NA_real_ else integer_value(switch(e$op,'+'=a$value+b$value,'-'=a$value-b$value,'*'=a$value*b$value))
 list(known=TRUE,value=value)
}
expr_names<-function(e) {if(e$kind=='variable') e$name else if(e$kind=='arithmetic') c(expr_names(e$left),expr_names(e$right)) else if(e$kind=='call') unlist(lapply(e$args,expr_names),use.names=FALSE) else character()}
expr_count<-function(e) if(e$kind=='arithmetic') 1L+expr_count(e$left)+expr_count(e$right) else if(e$kind=='call') 1L+sum(vapply(e$args,expr_count,0L)) else 0L
predicate<-function(text) {
 m<-match_parts('(.+?)\\s*(<=|>=|\\^=|~=|<>|=|<|>|\\b(?:eq|ne|lt|le|gt|ge)\\b)\\s*(.+)',text)
 if(is.null(m)) list(op='truth',left=expression(text)) else list(op=tolower(m[2]),left=expression(m[1]),right=expression(m[3]))
}
expanded<-function(text) {
 if(any(as.integer(charToRaw(text))>127)) stop('ASCII names');parts<-strsplit(trimws(gsub(' *- *','-',tolower(text))),' +')[[1]];result<-character()
 for(p in parts) {m<-match_parts('([a-z_][a-z0-9_]*?)([1-9][0-9]?)\u002d([a-z_][a-z0-9_]*?)([1-9][0-9]?)',p)
  if(is.null(m)) result<-c(result,p) else {a<-as.integer(m[2]);b<-as.integer(m[4]);if(m[1]!=m[3] || a>b || b>64) stop('range');result<-c(result,paste0(m[1],seq.int(a,b)))}
 }
 if(!length(result) || length(result)>64 || anyDuplicated(result) || any(!vapply(result,ordinary,FALSE))) stop('name list');result
}
selector<-function(text,option=FALSE) {m<-match_parts(if(option) '(keep|drop) *= *(.*)' else '(keep|drop) +(.*)',text);if(is.null(m)) stop('selection');list(mode=tolower(m[1]),names=expanded(m[2]))}
dataset<-function(text,keyword) {if(any(as.integer(charToRaw(text))>127)) stop('ASCII dataset');m<-match_parts(paste0(keyword,' +([a-z_][a-z0-9_]{0,31})(?: *\\((.*)\\))?'),text);if(is.null(m)) stop('dataset');name<-tolower(m[1]);if(!(ordinary(name) || keyword=='data' && name=='_null_')) stop('dataset name');list(name=name,selection=if(length(m)>1 && nzchar(m[2])) selector(m[2],TRUE) else NULL)}
select_names<-function(schema,s) {if(is.null(s)) return(schema);if(any(!(s$names %in% schema))) stop('unresolved selection');v<-schema[(schema %in% s$names)==(s$mode=='keep')];if(!length(v)) stop('empty selection');v}
number_spec<-function() list(type='number',length='-',label='-',format='-',keys=character())
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

number <- function(token) {
  if(nchar(token,type='bytes')<1 || nchar(token,type='bytes')>32) stop('token width')
  if(token=='.') return(NA_real_)
  if(!grepl('^[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?$',token,perl=TRUE)) stop('numeric syntax')
  pieces<-strsplit(tolower(token),'e',fixed=TRUE)[[1]]
  mantissa<-gsub('^[+-]','',pieces[1]);digits<-gsub('.','',mantissa,fixed=TRUE)
  exponent<-if(length(pieces)==2) as.numeric(pieces[2]) else 0
  if(nchar(digits)>15 || abs(exponent)>15) stop('digit/exponent bound')
  dot<-regexpr('.',mantissa,fixed=TRUE)[1]
  scale<-(if(dot>0) nchar(mantissa)-dot else 0)-exponent
  coefficient<-as.numeric(digits)
  # All coefficients below10^15 are exact binary integers. For a decimal
  # denominator10^scale, remove every factor5 or refuse a rounded value.
  if(coefficient!=0 && scale>0) for(k in seq_len(scale)) {
    if(coefficient%%5!=0) stop('rounded decimal')
    coefficient<-coefficient/5
  }
  value<-if(scale>0) coefficient/(2^scale) else coefficient*(10^(-scale))
  if(substr(token,1,1)=='-') value<- -value
  if(!is.finite(value) || abs(value)>2147483647) stop('range')
  integer_value(if(value==0) 0 else value)
}
read_records <- function(records,width) {
  if(width<1 || width>32 || width!=trunc(width) || length(records)>10000) stop('bounds')
  for(record in records) {
    bytes<-as.integer(charToRaw(record))
    if(length(bytes)>80 || any(bytes<32 | bytes>126) || grepl(';',record,fixed=TRUE)) stop('record')
  }
  rows<-list(); cursor<-1L
  while(cursor<=length(records)) {
    observation<-numeric()
    while(length(observation)<width && cursor<=length(records)) {
      fields<-strsplit(records[cursor],' +',perl=TRUE)[[1]];fields<-fields[nzchar(fields)]
      needed<-width-length(observation)
      if(length(fields)) observation<-c(observation,vapply(head(fields,needed),number,0.0))
      cursor<-cursor+1L
    }
    if(length(observation)==width) rows[[length(rows)+1L]]<-unname(observation)
  }
  rows
}
validate_calls<-function(body,flat,labels,has_input) {
 links<-Filter(function(op) op$kind=='link',flat);targets<-unique(vapply(links,function(op) op$name,''));if(length(targets)>1) stop('one LINK destination')
 target<-if(length(targets)) labels[[targets[1]]] else length(body)+1L
 has_link<-function(op) op$kind=='link' || any(vapply(c(if(is.null(op$body)) list() else op$body,if(is.null(op$otherwise)) list() else op$otherwise),has_link,FALSE))
 if(target<=length(body) && any(vapply(body[seq.int(target,length(body))],has_link,FALSE))) stop('LINK in target region')
 outcomes<-function(op) {
  if(op$kind %in% c('goto','link')) return(paste0(op$kind,':',op$name))
  if(op$kind %in% c('stop','return')) return(op$kind)
  if(op$kind=='if') return(unique(c(outcomes(op$body[[1]]),if(length(op$otherwise)) outcomes(op$otherwise[[1]]) else 'next')))
  if(op$kind %in% c('group','counted','while','until')) {result<-'next';for(child in op$body) if('next' %in% result) result<-unique(c(result[result!='next'],outcomes(child)));if(op$kind!='group') result<-unique(c(result,'next'));return(result)}
  'next'
 }
 edges<-lapply(body,outcomes);pending<-lapply(seq_along(body),function(pc) c(pc,0,0));pending[[length(pending)+1L]]<-c(1,0,1);seen<-new.env(hash=TRUE,parent=emptyenv());count<-0L
 while(length(pending)) {
  at<-length(pending);state<-pending[[at]];pending[[at]]<-NULL;key<-paste(state,collapse='/');if(exists(key,seen,inherits=FALSE)) next;assign(key,TRUE,seen);count<-count+1L;if(count>20000) stop('static caller budget');pc<-state[1];caller<-state[2];reachable<-state[3]
  push<-function(pc,caller) {pending[[length(pending)+1L]]<<-c(pc,caller,reachable)}
  if(pc>length(body)) {if(caller) push(caller,0);next}
  for(edge in edges[[pc]]) {
   if(edge=='next') push(pc+1,caller) else if(edge=='return') {if(caller) push(caller,0) else if(reachable && !has_input) stop('unlinked RETURN without INPUT')} else if(grepl('^(goto|link):',edge)) {parts<-strsplit(edge,':',fixed=TRUE)[[1]];if(parts[1]=='link') {if(caller) stop('nested active LINK');push(labels[[parts[2]]],pc+1)} else push(labels[[parts[2]]],caller)}
  }
 }
}
program<-function(path,folder) {
 scanned<-scan_source(path);statements<-scanned$statements;cursor<-1L;tables<-load_catalog(folder);logs<-character();trace_store<-new.env(hash=TRUE,parent=emptyenv());trace_count<-0L;accounts<-list();cat('STATEMENTS:',length(statements),'\n',sep='')
 while(cursor<=length(statements)) {
  header<-dataset(statements[cursor],'data');cursor<-cursor+1L;log_offset<-length(logs);retained<-list();arrays<-list();out_selection<-header$selection;input_selection<-NULL;input_name<-NULL;feature<-FALSE;seen_action<-FALSE;op_count<-0L;math_count<-0L
  end<-cursor;while(end<=length(statements) && tolower(statements[end])!='run') end<-end+1L
  if(end>length(statements)) stop('missing RUN')
  card<-which(tolower(statements[seq.int(cursor,end)]) %in% c('cards','datalines'))+cursor-1L
  if(length(card)>1L || length(card) && card!=end-1L) stop('one final inline block')
  data_records<-if(length(card)) scanned$records[[as.character(card)]] else NULL;input_names<-NULL;input_rows<-NULL;current_statement<-cursor
  discover_expr<-function(e,control=FALSE) {static(e,control);math_count<<-math_count+expr_count(e);invisible(NULL)}
  discover_test<-function(p) {discover_expr(p$left);if(p$op!='truth') discover_expr(p$right)}
  capture_count<-function(start,stop,by) {if(is.na(start) || is.na(stop) || is.na(by) || by==0) stop('counted controls');count<-if((stop-start)*by<0) 0 else floor((stop-start)/by)+1;if(count>10000) stop('counted bound');as.integer(count)}
  parse_body<-function(depth=0L,loops=character(),active=character(),closing=FALSE,jumps=TRUE) {
   if(depth>32) stop('mixed depth');body<-list()
   repeat {
    if(cursor>length(statements)) stop('missing terminator');text<-statements[cursor];current_statement<<-cursor;cursor<<-cursor+1L
    if(tolower(text)=='end') {if(!closing) stop('unmatched END');return(body)}
    if(tolower(text)=='run') {if(closing) stop('RUN before END');return(body)}
    if(tolower(text) %in% c('cards','datalines')) {if(depth || is.null(data_records)) stop('inline context');next}
    label<-match_parts('([a-z_][a-z0-9_]{0,31}) *: *(.*)',text)
    if(!is.null(label)) {if(depth || !ordinary(tolower(label[1]))) stop('label context');op_count<<-op_count+1L;body[[length(body)+1L]]<-list(kind='label',name=tolower(label[1]));text<-label[2];if(!nzchar(text)) next}
    body[[length(body)+1L]]<-parse_one(text,depth,loops,active,jumps=jumps)
   }
  }
  parse_one<-function(text,depth,loops,active,branch=FALSE,jumps=TRUE) {
   op_count<<-op_count+1L;if(depth>32 || op_count>1024 || nchar(text)>4096) stop('source bound')
   # Only quoted PUT text may contain non-ASCII bytes, and literal validation
   # below retains the existing printable-ASCII policy.
   if(any(as.integer(charToRaw(text))>127)) stop('ASCII control syntax')
   low<-tolower(text)
   if(depth>=32 && (low=='do' || grepl('^if +.+ +then +',low) || grepl('^do +',low))) stop('mixed container bound')
   if(low=='do') {feature<<-TRUE;seen_action<<-TRUE;return(list(kind='group',body=parse_body(depth+1L,loops,active,TRUE,FALSE)))}
   m<-match_parts('if +(.+?) +then +(.+)',text)
   if(!is.null(m)) {seen_action<<-TRUE;p<-predicate(m[1]);discover_test(p);action<-parse_one(m[2],depth+1L,loops,active,TRUE,jumps);otherwise<-NULL
    if(cursor<=length(statements)) {other<-match_parts('else +(.+)',statements[cursor]);if(!is.null(other)) {cursor<<-cursor+1L;otherwise<-parse_one(other[1],depth+1L,loops,active,TRUE,jumps)}}
    return(list(kind='if',test=p,body=list(action),otherwise=if(is.null(otherwise)) list() else list(otherwise)))}
   if(low %in% c('stop','return')) {seen_action<<-TRUE;return(list(kind=low))}
   jump<-match_parts('(go *to|link) +([a-z_][a-z0-9_]{0,31})',text)
   if(!is.null(jump)) {if(!jumps || length(loops) || !ordinary(tolower(jump[2]))) stop('jump context');seen_action<<-TRUE;return(list(kind=if(tolower(jump[1])=='link') 'link' else 'goto',name=tolower(jump[2])))}
   read<-match_parts('input +([a-z_][a-z0-9_]{0,31}(?: +[a-z_][a-z0-9_]{0,31})*)',text)
   if(!is.null(read)) {if(depth || branch || seen_action || !is.null(input_names) || is.null(data_records) || scanned$lines[card]+1L<=scanned$lines[current_statement]) stop('INPUT context');input_names<<-strsplit(tolower(read[1]),' +')[[1]];if(length(input_names)>32 || anyDuplicated(input_names) || any(!vapply(input_names,ordinary,FALSE))) stop('INPUT names');input_rows<<-lapply(read_records(data_records,length(input_names)),function(values) setNames(as.list(values),input_names));seen_action<<-TRUE;return(list(kind='input',names=input_names))}
   if(low %in% c('leave','continue')) {if(!length(loops)) stop('transfer ownership');feature<<-TRUE;seen_action<<-TRUE;return(list(kind=low))}
   conditional<-match_parts('do +(while|until) *\\((.*)\\)',text);counted<-match_parts('do +([a-z_][a-z0-9_]{0,31}) *= *(.+?) +to +(.+?)(?: +by +(.+))?',text)
   if(!is.null(conditional) || !is.null(counted)) {
    if(branch || length(loops)>=8 || length(loops) && (is.null(counted) || any(loops!='counted'))) stop('loop nesting');seen_action<<-TRUE
    if(!is.null(conditional)) {kind<-tolower(conditional[1]);p<-predicate(conditional[2]);discover_test(p);return(list(kind=kind,test=p,body=parse_body(depth+1L,c(loops,kind),active,TRUE,FALSE)))}
    index<-tolower(counted[1]);if(!ordinary(index) || index %in% active) stop('control index');terms<-c(counted[2],counted[3],if(length(counted)>3 && nzchar(counted[4])) counted[4] else '1');controls<-lapply(terms,expression,control=TRUE)
    for(e in controls) {discover_expr(e,TRUE);if(index %in% expr_names(e)) stop('self control')}
    known<-lapply(controls,static,control=TRUE);if(known[[3]]$known && known[[3]]$value==0) stop('zero BY');if(all(vapply(known,function(x) x$known,FALSE))) capture_count(known[[1]]$value,known[[2]]$value,known[[3]]$value)
    return(list(kind='counted',index=index,controls=controls,body=parse_body(depth+1L,c(loops,'counted'),c(active,index),TRUE,FALSE)))}
   if(grepl('^set +',low,perl=TRUE)) stop('SET outside flow profile')
   m<-match_parts('retain +([a-z_][a-z0-9_]{0,31}) +(.+)',text)
   if(!is.null(m)) {name<-tolower(m[1]);value<-expression(m[2]);if(depth || branch || seen_action || !ordinary(name) || name %in% names(retained) || value$kind!='number' && !(value$kind=='arithmetic' && value$op=='-' && value$left$kind=='number' && value$left$value==0 && value$right$kind=='number')) stop('RETAIN literal');s<-static(value);if(!s$known) stop('RETAIN literal');retained[[name]]<<-s$value;return(list(kind='declare',name=name))}
   if(grepl('^(keep|drop) +',low,perl=TRUE)) {if(depth || branch || !is.null(out_selection)) stop('selector context');out_selection<<-selector(text);return(list(kind='declare_selection'))}
   seen_action<<-TRUE
   if(low=='output' || grepl('^output +',low)) {target<-if(low=='output') header$name else sub('^output +','',low);if(target!=header$name || target=='_null_') stop('OUTPUT target');return(list(kind='output'))}
   m<-match_parts('put +((?:[a-z_][a-z0-9_]{0,31} *= *)+)',text)
   if(!is.null(m)) {parts<-regmatches(tolower(m[1]),gregexpr('[a-z_][a-z0-9_]{0,31}',tolower(m[1]),perl=TRUE))[[1]];if(any(!vapply(parts,ordinary,FALSE)) || nchar(paste(paste0(parts,'=.'),collapse=' '))>64) stop('named PUT');return(list(kind='put_named',names=parts))}
   m<-match_parts('put +([a-z_][a-z0-9_]{0,31}(?: +[a-z_][a-z0-9_]{0,31})*)',text)
   if(!is.null(m)) {parts<-strsplit(tolower(m[1]),' +')[[1]];if(any(!vapply(parts,ordinary,FALSE)) || length(parts)*2>64) stop('numeric PUT');return(list(kind='put_list',names=parts))}
   if(grepl('^put +',low)) {rest<-sub('^[Pp][Uu][Tt] +','',text);pattern<-"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"";parts<-regmatches(rest,gregexpr(pattern,rest,perl=TRUE))[[1]];if(!length(parts) || nzchar(trimws(gsub(pattern,'',rest,perl=TRUE)))) stop('literal PUT');values<-vapply(parts,function(p) {q<-substr(p,1,1);b<-substr(p,2,nchar(p)-1);if(q=='"' && grepl('[&%]',b)) stop('macro quote');if(!nzchar(b)) q else gsub(paste0(q,q),q,b,fixed=TRUE)},'');value<-paste0(values,collapse='');if(nchar(value)>64 || any(as.integer(charToRaw(value))<32 | as.integer(charToRaw(value))>126)) stop('literal text');return(list(kind='put_literal',value=value))}
   m<-match_parts('if +(.+)',text)
   if(!is.null(m)) {if(length(loops)) stop('loop subset');p<-predicate(m[1]);discover_test(p);return(list(kind='subset',test=p))}
   assignment<-match_parts('([a-z_][a-z0-9_]{0,31}) *= *(.+)',text);summation<-match_parts('([a-z_][a-z0-9_]{0,31}) *\\+ *(.+)',text)
   if(!is.null(assignment) || !is.null(summation)) {m<-if(!is.null(assignment)) assignment else summation;name<-tolower(m[1]);if(!ordinary(name) || name %in% active) stop('assignment name');e<-expression(m[2]);discover_expr(e);if(is.null(assignment) && !(name %in% names(retained))) retained[[name]]<<-0;return(list(kind=if(is.null(assignment)) 'sum' else 'assign',name=name,value=e))}
   stop(paste('unsupported statement',text))
  }
  body<-parse_body();if(math_count>128 || op_count>1024 || !is.null(data_records) && is.null(input_names)) stop('profile expression/input bound');body<-c(list(list(kind='profile')),if(is.null(header$selection)) list() else list(list(kind='declare_selection')),body);schema<-list();source<-NULL;puts<-list();explicit<-FALSE
  add<-function(name) if(name!='_n_' && is.null(schema[[name]])) schema[[name]]<<-number_spec()
  discover<-function(body) for(op in body) {
   if(op$kind=='read') {source<<-tables[[input_name]];if(is.null(source)) stop('SET absent');names<-select_names(names(source$schema),input_selection);source$schema<<-source$schema[names];source$rows<<-lapply(source$rows,function(row) row[names]);if(length(source$rows)>10000) stop('SET rows');for(n in names) {if(!ordinary(n) || !(source$schema[[n]]$type %in% c('number','typed-number'))) stop('SET numeric');schema[[n]]<<-source$schema[[n]]};for(row in source$rows) for(x in row) integer_value(x)}
   if(op$kind=='input') for(n in op$names) add(n)
   if(op$kind %in% c('declare','assign','sum')) add(op$name)
   if(op$kind=='counted') {add(op$index);for(e in op$controls) for(n in expr_names(e)) add(n)}
   if(!is.null(op$value) && is.list(op$value)) for(n in expr_names(op$value)) add(n)
   if(!is.null(op$test)) {for(n in expr_names(op$test$left)) add(n);if(op$test$op!='truth') for(n in expr_names(op$test$right)) add(n)}
   if(op$kind=='output') explicit<<-TRUE
   if(op$kind %in% c('put_named','put_list')) puts[[length(puts)+1L]]<<-op
   if(!is.null(op$body)) discover(op$body)
   if(!is.null(op$otherwise)) discover(op$otherwise)
  }
  discover(body);if(!length(schema) || length(schema)>64) stop('PDV bound');chosen<-select_names(names(schema),out_selection)
  for(op in puts) for(n in op$names) if(!(n %in% names(schema)) || !(schema[[n]]$format %in% c('-',''))) stop('PUT complete unformatted schema')
  flat<-list();flatten<-function(ops) for(op in ops) {flat[[length(flat)+1L]]<<-op;if(!is.null(op$body)) flatten(op$body);if(!is.null(op$otherwise)) flatten(op$otherwise)};flatten(body)
  if(!any(vapply(flat,function(op) op$kind %in% c('label','goto','link','return','stop'),FALSE))) stop('actual flow trigger required')
  labels<-list();for(pos in seq_along(body)) if(body[[pos]]$kind=='label') {name<-body[[pos]]$name;if(name %in% names(labels)) stop('duplicate label');labels[[name]]<-pos}
  if(length(labels)>64) stop('label bound')
  for(op in flat) if(op$kind %in% c('goto','link') && !(op$name %in% names(labels))) stop('undefined label')
  input_pos<-which(vapply(body,function(op) op$kind=='input',FALSE))
  if(length(input_pos)) {if(any(!vapply(body[seq_len(input_pos-1L)],function(op) op$kind %in% c('profile','declare','declare_selection'),FALSE))) stop('INPUT prefix');for(op in flat) if(op$kind %in% c('goto','link') && labels[[op$name]]<=input_pos) stop('INPUT reentry')}
  validate_calls(body,flat,labels,length(input_pos)>0L)
  input<-if(is.null(input_names)) list(list()) else input_rows;output<-list();events<-0L;trips<-0L;iteration<-0L;instructions<-0L
  charge<-function() {instructions<<-instructions+1L;if(instructions>100000) stop('instruction budget')}
  event<-function(...) {events<<-events+1L;if(events>1000000) stop('event budget');trace_count<<-trace_count+1L;assign(as.character(trace_count),paste(...,sep='|'),trace_store)}
  eval<-function(e) {if(e$kind=='number') return(e$value);if(e$kind=='variable') return(integer_value(if(e$name=='_n_') iteration else row[[e$name]]));if(e$kind=='call') {a<-eval(e$args[[1]]);b<-eval(e$args[[2]]);if(is.na(a) || is.na(b) || b==0) stop('MOD runtime domain');return(integer_value(a-trunc(a/b)*b))};a<-eval(e$left);b<-eval(e$right);if(is.na(a) || is.na(b)) NA_real_ else integer_value(switch(e$op,'+'=a+b,'-'=a-b,'*'=a*b))}
  test<-function(p) {a<-eval(p$left);if(p$op=='truth') return(!is.na(a) && a!=0);b<-eval(p$right);if(is.na(a) || is.na(b)) {if(is.na(a) && is.na(b)) {a<-0;b<-0} else {if(is.na(a)) a<- -Inf;if(is.na(b)) b<- -Inf}};switch(p$op,'='=a==b,eq=a==b,ne=a!=b,'^='=a!=b,'~='=a!=b,'<>'=a!=b,'<'=a<b,lt=a<b,'<='=a<=b,le=a<=b,'>'=a>b,gt=a>b,'>='=a>=b,ge=a>=b)}
  snapshot<-function() {if(length(output)>=10000) stop('OUTPUT bound');output[[length(output)+1L]]<<-row[chosen];event('output',paste(vapply(chosen,function(n) paste0(n,'=',show(row[[n]])),''),collapse=';'))}
  perform<-function(body) {
   for(op in body) {
    charge();kind<-op$kind
    if(kind %in% c('profile','declare','declare_selection')) next
    if(kind=='input') {for(n in op$names) row[[n]]<<-incoming[[n]];event('input',paste(vapply(op$names,function(n) paste0(n,'=',show(row[[n]])),''),collapse=';'));next}
    if(kind=='label') {event('label',op$name);next}
    if(kind %in% c('goto','link')) {event(kind,op$name);return(paste0(kind,':',op$name))}
    if(kind %in% c('stop','return')) {event(kind);return(kind)}
    if(kind=='assign') {row[[op$name]]<<-eval(op$value);event('assign',op$name,show(row[[op$name]]))}
    else if(kind=='sum') {x<-eval(op$value);old<-row[[op$name]];row[[op$name]]<<-integer_value((if(is.na(x)) 0 else x)+(if(is.na(old)) 0 else old));event('sum',op$name,show(row[[op$name]]))}
    else if(kind=='group') {event('group','enter');signal<-perform(op$body);event('group','exit');if(signal!='normal') return(signal)}
    else if(kind=='if') {value<-test(op$test);event('if',as.integer(value));signal<-perform(if(value) op$body else op$otherwise);if(signal!='normal') return(signal)}
    else if(kind=='subset') {value<-test(op$test);event('subset',as.integer(value));if(!value) return('reject')}
    else if(kind %in% c('leave','continue')) {event('transfer',kind);return(kind)}
    else if(kind=='counted') {controls<-vapply(op$controls,eval,0.0);for(x in controls) integer_value(x);count<-capture_count(controls[1],controls[2],controls[3]);spent<<-spent+count;if(spent>10000) stop('shared counted budget');row[[op$index]]<<-integer_value(controls[1]);event('capture',op$index,show(controls[1]),show(controls[2]),show(controls[3]),count);left<-FALSE
     if(count) for(k in seq_len(count)) {value<-controls[1]+(k-1)*controls[3];row[[op$index]]<<-integer_value(value);trips<<-trips+1L;event('iteration','counted',op$index,show(value));signal<-perform(op$body);if(!(signal %in% c('normal','leave','continue'))) return(signal);if(signal=='leave') {left<-TRUE;break};charge();row[[op$index]]<<-integer_value(value+controls[3]);event('increment',op$index,show(row[[op$index]]))}
     if(!left) row[[op$index]]<<-integer_value(controls[1]+count*controls[3]);event('loop','exit','counted')}
    else if(kind %in% c('while','until')) {local<-0L;repeat {if(kind=='while') {charge();value<-test(op$test);event('test','while',as.integer(value));if(!value) break};local<-local+1L;if(local>10000) stop('conditional budget');trips<<-trips+1L;event('iteration',kind,local);signal<-perform(op$body);if(!(signal %in% c('normal','leave','continue'))) return(signal);if(signal=='leave') break;if(kind=='until') {charge();value<-test(op$test);event('test','until',as.integer(value));if(value) break}};event('loop','exit',kind)}
    else if(kind=='output') snapshot()
    else if(kind %in% c('put_named','put_list','put_literal')) {if(length(logs)-log_offset>=10000) stop('PUT count');text<-if(kind=='put_literal') op$value else if(kind=='put_named') paste(vapply(op$names,function(n) paste0(n,'=',show(row[[n]])),''),collapse=' ') else paste0(paste(vapply(row[op$names],show,''),collapse=' '),' ');if(nchar(text)>64) stop('PUT width');logs<<-c(logs,text);event('put',hex(text))}
    else stop('unhandled action')
   }
   'normal'
  }
  for(incoming in input) {
   iteration<-iteration+1L;spent<-0L;row<-setNames(as.list(rep(NA_real_,length(schema))),names(schema));row[names(retained)]<-retained;event('row',iteration);pc<-1L;caller<-0L;stopped<-FALSE;signal<-'normal'
   repeat {
    if(pc>length(body)) {if(caller==0L) break;charge();event('resume','implicit',caller-1L);pc<-caller;caller<-0L;next}
    event('pc',pc-1L);signal<-perform(list(body[[pc]]))
    if(grepl('^(goto|link):',signal)) {parts<-strsplit(signal,':',fixed=TRUE)[[1]];if(parts[1]=='link') {if(caller!=0L) stop('one active caller');caller<-pc+1L;event('call',caller-1L)};pc<-labels[[parts[2]]];next}
    if(signal=='return') {if(caller==0L) {signal<-'normal';event('next-record');break};event('resume','explicit',caller-1L);pc<-caller;caller<-0L;next}
    if(signal=='stop') {stopped<-TRUE;break}
    if(signal=='reject') break
    if(signal!='normal') stop('escaped loop transfer')
    pc<-pc+1L
   }
   retained<-row[names(retained)];if(!stopped && signal=='normal' && !explicit && header$name!='_null_') snapshot();if(stopped) break
  }
  table<-list(schema=schema[chosen],rows=output,encoding=if(is.null(source)) '-' else source$encoding,label=if(is.null(source)) '-' else source$label,keys=c(if(is.null(source)) character() else source$keys[!(source$keys %in% c('schema','rows'))],'schema','rows'))
  if(header$name!='_null_') tables[[header$name]]<-table
  accounts[[length(accounts)+1L]]<-list(name=header$name,iterations=iteration,trips=trips)
 }
 for(name in names(tables)) {
  t<-tables[[name]];cat('TABLE:',name,'\nMETA:',t$encoding,'|',t$label,'\nTABLEKEYS:',paste(t$keys,collapse='|'),'\n',sep='')
  for(n in names(t$schema)) {d<-t$schema[[n]];cat('COLUMN:',paste(c(n,d$type,d$length,d$label,d$format),collapse='|'),'\n',sep='');if(length(d$keys)) cat('COLUMNKEYS:',paste(c(n,d$keys),collapse='|'),'\n',sep='')}
  for(row in t$rows) {cat('ROWKEYS:',paste(names(row),collapse='|'),'\n',sep='');cat('ROW:',paste(vapply(row,function(x) if(inherits(x,'sas_tag')) paste0('T',x$tag) else if(is.character(x)) paste0('C',hex(x)) else if(is.na(x)) 'M' else paste0('N',sprintf('%.17g',x)),''),collapse=','),'\n',sep='')}
 }

 for(a in accounts) cat('ACCOUNT:',a$name,',',a$iterations,',',a$trips,'\n',sep='')
 for(l in logs) cat('LOG:',hex(l),'\n',sep='')
 for(i in seq_len(trace_count)) cat('TRACE:',hex(get(as.character(i),trace_store)),'\n',sep='')
}
args<-commandArgs(trailingOnly=TRUE)
if(length(args)==3 && args[1]=='program') program(args[2],args[3]) else if(length(args)==2 && args[1]=='batch') {
 cases<-read.csv(file.path(args[2],'cases.csv'),colClasses='character')
 for(i in seq_len(nrow(cases))) {cat('CASE:',i-1L,'\n',sep='');good<-tryCatch({program(file.path(args[2],cases$source[i]),file.path(args[2],cases$catalog[i]));TRUE},error=function(e) {cat('REASON:',conditionMessage(e),'\n',sep='');FALSE});cat('ANSWER:',if(good) 'OK' else 'REFUSE','\n',sep='')}
} else stop('program source catalog-folder or batch folder')
