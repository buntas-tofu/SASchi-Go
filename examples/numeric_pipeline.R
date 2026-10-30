# Independent complete-source numeric pipeline witness; base R only.
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
  if(value==0) 0 else value
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
# Independent rounded-row and projection witness for maintainer review.
# Reuses independent base-R numeric helpers; no live SAS or physical log claim.
# Rounded scalar source/control witness for principal and maintainer review.
# Independent base-R testbed evidence; no live SAS or physical SAS log claim.
limit <- 2147483647
normal <- .Machine$double.xmin
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
number_text <- function(x) if(is.na(x)) '.' else sprintf('%.17g',x)
numeric_operand <- function(x) {
  if(is.nan(x)) stop('NaN is not ordinary missing')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || abs(x)>limit || (x!=0 && abs(x)<normal)) stop('numeric bound')
  if(x==0) 0 else x
}
bound <- function(kind,text) {
  if(kind=='missing') return(NA_real_)
  if(kind!='number') stop('ordinary numeric operand required')
  numeric_operand(suppressWarnings(as.numeric(text)))
}
arithmetic <- function(op,a,b) {
  a <- numeric_operand(a);b <- numeric_operand(b)
  if(op=='**' && !is.na(b) && (b!=trunc(b) || b<0 || b>32 || (!is.na(a) && a==0 && b==0))) stop('power domain')
  if(op=='/' && !is.na(b) && b==0) stop('division domain')
  if(is.na(a) || is.na(b)) return(NA_real_)
  q <- switch(op,'+'=a+b,'-'=a-b,'*'=a*b,'/'=a/b,'**'=a^b,stop('operator'))
  if(q==0 && a!=0 && b!=0 && op %in% c('*','/','**')) stop('underflow')
  numeric_operand(q)
}
call <- function(name,values) {
  if(name=='constant') {
    if(length(values)!=1L || !identical(values[[1]],'pi')) stop('constant domain')
    return(pi)
  }
  if(length(values)!=1L) stop('arity')
  x <- numeric_operand(values[[1]])
  if(name=='int') {if(is.na(x) || (x!=trunc(x) && abs(x-round(x))<=2e-12)) stop('INT conservative boundary');return(trunc(x))}
  if(is.na(x)) return(NA_real_)
  if(name %in% c('sin','cos') && abs(x)>pi) stop('radian domain')
  if(name=='tan' && abs(x)>pi/4) stop('tangent domain')
  if(name %in% c('arsin','arcos') && abs(x)>1) stop('inverse domain')
  value <- switch(name,sin=sin(x),cos=cos(x),tan=tan(x),arsin=asin(x),
                  arcos=acos(x),atan=atan(x),stop('function'))
  numeric_operand(value)
}
logical_number <- function(x) {
  if(is.na(x)) return('.')
  if(!is.finite(x)) stop('output finite')
  if(x==0) return('0')
  if(x==trunc(x)) {
    if(abs(x)>99999999999) stop('output integer magnitude')
    return(sprintf('%.0f',x))
  }
  if(abs(x)<1e-4 || abs(x)>=1e9) stop('output fraction magnitude')
  width <- nchar(sprintf('%.0f',trunc(abs(x))))
  places <- 12L-as.integer(x<0)-width-1L
  fmt <- paste0('%.',places,'f')
  token <- sprintf(fmt,x)
  if(nchar(token)>12L) stop('output carry width')
  # Different host-language rounding with a conservative17ULP stability witness.
  # The implementation's exact rational guard is16ULP; these cases stay clear.
  exponent <- as.numeric(strsplit(sprintf('%a',abs(x)),'p',fixed=TRUE)[[1]][2])
  step <- 2^(exponent-52)
  if(sprintf(fmt,x-17*step)!=token || sprintf(fmt,x+17*step)!=token) stop('decimal midpoint')
  token <- sub('0+$','',token);token <- sub('\\.$','',token)
  if(token=='-0') '0' else token
}
record <- function(values) {
  text <- paste0(paste(vapply(values,logical_number,''),collapse=' '),' ')
  if(nchar(text)>64L) stop('output row width')
  text
}
capture <- function(pattern,text) {
  match <- regmatches(text,regexec(paste0('(?i)^',pattern,'$'),text,perl=TRUE))[[1]]
  if(length(match)) match[-1] else NULL
}
scan_program <- function(path) {
  lines<-readLines(path,warn=FALSE);code<-paste(lines,collapse='\n')
  chars<-strsplit(code,'',fixed=TRUE)[[1]];i<-1L;n<-length(chars)
  statements<-character();buffer<-'';quote<-'';comment<-FALSE;records<-list()
  while(i<=n) {
    ch<-chars[i];nextch<-if(i<n) chars[i+1L] else ''
    if(comment) {
      if(ch=='*' && nextch=='/') {comment<-FALSE;i<-i+2L;buffer<-paste0(buffer,' ')} else i<-i+1L
      next
    }
    if(nzchar(quote)) {
      buffer<-paste0(buffer,ch)
      if(ch==quote) {
        if(nextch==quote) {buffer<-paste0(buffer,nextch);i<-i+1L} else quote<-''
      }
      i<-i+1L;next
    }
    if(ch=='/' && nextch=='*') {comment<-TRUE;i<-i+2L;next}
    if(ch %in% c("'",'"')) {quote<-ch;buffer<-paste0(buffer,ch);i<-i+1L;next}
    if(ch!=';') {if(grepl('[[:space:]]',ch)) ch<-' ';buffer<-paste0(buffer,ch);i<-i+1L;next}
    statement<-trimws(buffer);buffer<-'';i<-i+1L
    if(!nzchar(statement)) stop('unexpected null code statement')
    statements<-c(statements,statement)
    if(tolower(statement) %in% c('cards','datalines')) {
      tail<-paste(chars[i:n],collapse='');physical<-strsplit(paste0(tail,'\nEND'),'\n',fixed=TRUE)[[1]]
      if(nzchar(trimws(physical[1],whitespace=' '))) stop('inline header')
      end<-which(grepl('^ *; *$',physical))
      if(!length(end)) stop('inline terminator')
      end<-end[1];records[[as.character(length(statements))]]<-if(end>2) physical[2:(end-1)] else character()
      consumed<-sum(nchar(physical[seq_len(end)],type='chars'))+end
      i<-i+consumed
    }
  }
  if(comment || nzchar(quote) || nzchar(trimws(buffer))) stop('unconsumed source')
  list(statements=statements,records=records)
}
parse_expr <- function(text) {
  pattern <- "'[^']*'|\"[^\"]*\"|[0-9]+(?:\\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\\.[0-9]+(?:[eE][+-]?[0-9]+)?|[a-z_]\\w*|\\*\\*|[.(),+*/{}\\[\\]-]"
  tokens <- regmatches(tolower(text),gregexpr(pattern,tolower(text),perl=TRUE))[[1]]
  if(!length(tokens) || paste(tokens,collapse='')!=gsub('[[:space:]]','',tolower(text))) stop('expression tokens')
  at <- 1L
  peek <- function() if(at<=length(tokens)) tokens[at] else ''
  take <- function(expected=NULL) {
    if(at>length(tokens)) stop('expression ends early')
    x <- tokens[at];at <<- at+1L
    if(!is.null(expected) && x!=expected) stop('required expression token')
    x
  }
  atom <- function() {
    x <- take()
    if(x=='(') {value <- expression();take(')');return(value)}
    if(x=='.') return(list(kind='number',value=NA_real_))
    if(grepl('^[0-9.]',x)) return(list(kind='number',value=numeric_operand(as.numeric(x))))
    if(substr(x,1,1) %in% c("'",'"')) return(list(kind='string',value=substr(x,2,nchar(x)-1)))
    if(!grepl('^[a-z_]\\w*$',x,perl=TRUE)) stop('primary token')
    if(x=='sum' && peek()=='(' && at+1L<=length(tokens) && tokens[at+1L]=='of') {
      take('(');take('of');name<-take();open<-take();close<-if(open=='{') '}' else if(open=='[') ']' else if(open=='(') ')' else stop('OF bounds')
      take('*');take(close);take(')');return(list(kind='array_sum',name=name))
    }
    if(peek() %in% c('{','[')) {
      open<-take();index<-expression();take(if(open=='{') '}' else ']')
      return(list(kind='array_get',name=x,index=index))
    }
    if(peek()=='(') {
      take('(');args <- list()
      if(peek()!=')') {
        args[[1]] <- expression()
        while(peek()==',') {take(',');args[[length(args)+1L]] <- expression()}
      }
      take(')');return(list(kind='call',name=x,args=args))
    }
    list(kind='variable',name=x)
  }
  power <- function() {
    if(peek() %in% c('+','-')) {op <- take();return(list(kind='unary',op=op,value=power()))}
    value <- atom()
    if(peek()=='**') {take('**');value <- list(kind='binary',op='**',left=value,right=power())}
    value
  }
  product <- function() {
    value <- power()
    while(peek() %in% c('*','/')) {op <- take();value <- list(kind='binary',op=op,left=value,right=power())}
    value
  }
  expression <- function() {
    value <- product()
    while(peek() %in% c('+','-')) {op <- take();value <- list(kind='binary',op=op,left=value,right=product())}
    value
  }
  value <- expression();if(at<=length(tokens)) stop('unconsumed expression');value
}

ordinary<-function(x) grepl('^[a-z_][a-z0-9_]{0,31}$',x,perl=TRUE) &&
  !(x %in% c('_n_','_error_','_all_','_numeric_','_character_','_temporary_',
             '_infile_','_file_','_ods_','_page_','_blankpage_'))
expand<-function(text,max_names=64L) {
  if(any(as.integer(charToRaw(text))>127)) stop('ASCII names')
  text<-tolower(trimws(gsub(' *- *','-',text)))
  tokens<-strsplit(text,' +',perl=TRUE)[[1]];answer<-character()
  for(token in tokens) {
    pair<-strsplit(token,'-',fixed=TRUE)[[1]]
    if(length(pair)==1 && ordinary(token)) answer<-c(answer,token) else {
      if(length(pair)!=2) stop('range')
      suffix<-sub('^.*?([0-9]+)$','\\1',pair,perl=TRUE)
      prefix<-sub('[0-9]+$','',pair)
      if(any(!grepl('^[1-9][0-9]*$',suffix)) || prefix[1]!=prefix[2] ||
         any(nchar(suffix)>10) || any(!vapply(pair,ordinary,FALSE))) stop('range')
      lo<-as.integer(suffix[1]);hi<-as.integer(suffix[2])
      if(lo>hi || lo<1 || hi-lo+1>max_names || (max_names==64L && hi>64)) stop('range bounds')
      answer<-c(answer,paste0(prefix[1],seq.int(lo,hi)))
    }
  }
  if(!length(answer) || length(answer)>max_names || anyDuplicated(answer) ||
     any(!vapply(answer,ordinary,FALSE))) stop('list')
  answer
}
select<-function(schema,mode,names) {
  if(is.null(mode)) return(schema)
  if(!(mode %in% c('keep','drop')) || any(!(names %in% schema))) stop('unresolved')
  selected<-schema[(schema %in% names)==(mode=='keep')]
  if(!length(selected)) stop('empty')
  selected
}
selection<-function(text,option=FALSE) {
  pattern<-if(option) '^(keep|drop) *= *(.*)$' else '^(keep|drop) +(.*)$'
  fields<-regmatches(tolower(trimws(text)),regexec(pattern,tolower(trimws(text)),perl=TRUE))[[1]]
  if(length(fields)!=3) stop('selection')
  list(mode=fields[2],names=expand(fields[3]))
}
choose<-function(schema,p) if(is.null(p)) schema else select(schema,p$mode,p$names)
dataset<-function(text,keyword) {
  fields<-regmatches(text,regexec(paste0('^',keyword,' +([a-z_][a-z0-9_]*)(?: *\\((.*)\\))?$'),
                                  text,perl=TRUE))[[1]]
  if(!length(fields)) stop('dataset')
  list(name=fields[2],projection=if(length(fields)>2 && nzchar(fields[3])) selection(fields[3],TRUE) else NULL)
}

load_catalog <- function(folder) {
  descriptors <- read.csv(file.path(folder,'descriptors.csv'),colClasses='character',na.strings=NULL)
  values <- read.csv(file.path(folder,'values.csv'),colClasses='character',na.strings=NULL)
  tables <- list()
  for(i in seq_len(nrow(descriptors))) {
    d <- descriptors[i,];name <- d$table
    if(!(d$type %in% c('number','typed-number','character')) ||
       (d$type %in% c('number','typed-number') && !(d$length %in% c('-','8'))) ||
       (d$type=='character' && (d$length=='-' || as.numeric(d$length)<1 || as.numeric(d$length)>32767))) stop('generic descriptor')
    if(is.null(tables[[name]])) tables[[name]] <- list(schema=list(),rows=list(),encoding=d$encoding,label=d$dataset_label)
    tables[[name]]$schema[[d$name]] <- as.list(d[c('type','length','label','format')])
  }
  for(i in seq_len(nrow(values))) {
    d <- values[i,];table <- tables[[d$table]];position <- as.integer(d$row)
    if(length(table$rows)<position) table$rows[[position]] <- list()
    spec <- table$schema[[d$name]]
    if(d$kind=='missing') value <- NA_real_
    else if(d$kind=='number') {
      value <- as.numeric(d$value)
      if(!is.finite(value)) stop('generic finite input')
    } else if(d$kind=='character' && spec$type=='character') {
      if(nchar(d$value,type='bytes')>as.integer(spec$length)) stop('generic input width')
      value <- paste0(d$value,strrep(' ',as.integer(spec$length)-nchar(d$value,type='bytes')))
    } else stop('generic imported type')
    table$rows[[position]][[d$name]] <- value;tables[[d$table]] <- table
  }
  for(name in names(tables)) {
    table <- tables[[name]]
    for(row in table$rows) if(!setequal(names(row),names(table$schema))) stop('generic row shape')
  }
  tables
}
encode_row <- function(row) paste(vapply(row,function(x) {
  if(is.character(x)) paste0('C',hex(x)) else if(is.na(x)) 'M' else paste0('N',sprintf('%.17g',x))
},''),collapse=',')
number_spec <- function() list(type='number',length='-',label='-',format='-')
parts <- function(x) {
  if(x==0) return(list(bits=integer(),power=0))
  h <- strsplit(sprintf('%a',abs(x)),'p',fixed=TRUE)[[1]]
  mantissa <- sub('^0x','',h[1]); dot <- regexpr('.',mantissa,fixed=TRUE)[1]
  fraction <- if(dot>0) nchar(mantissa)-dot else 0L
  digits <- strsplit(gsub('.','',mantissa,fixed=TRUE),'',fixed=TRUE)[[1]]
  table <- c('0000','0001','0010','0011','0100','0101','0110','0111',
             '1000','1001','1010','1011','1100','1101','1110','1111')
  bits <- as.integer(strsplit(paste(table[match(digits,c(as.character(0:9),letters[1:6]))],collapse=''),'',fixed=TRUE)[[1]])
  bits <- bits[min(which(bits==1L)):length(bits)]
  power <- as.numeric(h[2])-4*fraction
  while(tail(bits,1)==0L) {bits <- head(bits,-1);power <- power+1}
  list(bits=bits,power=power)
}
bit_product <- function(a,b) {
  # Bit positions and carries remain tiny exact integers even for106-bit products.
  x <- rev(a); y <- rev(b); digits <- integer(length(x)+length(y)+1L)
  for(i in which(x==1L)) for(j in which(y==1L)) digits[i+j-1L] <- digits[i+j-1L]+1L
  for(i in seq_len(length(digits)-1L)) {
    digits[i+1L] <- digits[i+1L]+digits[i]%/%2L
    digits[i] <- digits[i]%%2L
  }
  while(tail(digits,1)==0L) digits <- head(digits,-1)
  rev(digits)
}
multiply <- function(a,b) {
  for(x in c(a,b)) if(!is.na(x) && (!is.finite(x) || abs(x)>limit)) stop('range')
  if(is.na(a) || is.na(b)) return(NA_real_)
  q <- a*b
  if(!is.finite(q) || abs(q)>limit) stop('product range')
  if(a==0 || b==0) return(0)
  if(q==0) stop('underflow')
  ap <- parts(a);bp <- parts(b);qp <- parts(q)
  exact <- bit_product(ap$bits,bp$bits)
  if(!identical(exact,qp$bits) || ap$power+bp$power!=qp$power) stop('rounded product')
  q
}
add <- function(a,b,subtract=FALSE) {
  if(is.na(a) || is.na(b)) return(NA_real_)
  if(subtract) b <- -b
  s <- a+b; z <- s-a; residual <- (a-(s-z))+(b-z)
  if(!is.finite(s) || abs(s)>limit || residual!=0) stop('rounded or unbounded sum')
  if(s==0) 0 else s
}


program <- function(path,folder) {
  parsed<-scan_program(path);statements<-parsed$statements;at<-1L
  tables<-load_catalog(folder);logs<-character();accounts<-list()
  cat('STATEMENTS:',length(statements),'\n',sep='')
  while(at<=length(statements)) {
    header<-dataset(tolower(statements[at]),'data');at<-at+1L
    name<-header$name;schema<-list();retained<-list();arrays<-list();outp<-header$projection
    input<-list(list());input_names<-character();inline_names<-NULL;explicit<-FALSE;seen_executable<-FALSE
    source_metadata<-list(encoding='-',label='-');parsing_alias<-NULL;parsing_loop<-character();active_indices<-character();over_seen<-FALSE
    add_name<-function(n,spec=number_spec()) {
      if(n=='_n_') return(invisible(NULL))
      if(!ordinary(n) || (n=='_i_' && over_seen)) stop('ordinary numeric target/name required')
      if(n %in% names(arrays)) stop('array scalar collision')
      if(is.null(schema[[n]])) schema[[n]]<<-spec
    }
    constant_expr<-function(expr) {
      if(expr$kind %in% c('number','string')) return(list(known=TRUE,value=expr$value))
      if(expr$kind %in% c('variable','array_get','array_sum')) return(list(known=FALSE))
      if(expr$kind=='unary') {
        child<-constant_expr(expr$value)
        return(if(child$known) list(known=TRUE,value=if(expr$op=='-') -child$value else child$value) else list(known=FALSE))
      }
      if(expr$kind=='binary') {
        a<-constant_expr(expr$left);b<-constant_expr(expr$right)
        if(expr$op=='/' && b$known && !is.na(b$value) && b$value==0) stop('static divisor')
        if(expr$op=='**' && b$known && !is.na(b$value) && (b$value!=trunc(b$value) || b$value<0 || b$value>32)) stop('static exponent')
        return(if(a$known && b$known) list(known=TRUE,value=arithmetic(expr$op,a$value,b$value)) else list(known=FALSE))
      }
      if(expr$kind=='call') {
        if(!(expr$name %in% c('constant','sin','cos','tan','arsin','arcos','atan','int')) || length(expr$args)!=1L) stop('static call name/arity')
        if(expr$name=='constant' && (expr$args[[1]]$kind!='string' || expr$args[[1]]$value!='pi')) stop('constant literal')
        values<-lapply(expr$args,constant_expr)
        return(if(all(vapply(values,function(x) x$known,FALSE))) list(known=TRUE,value=call(expr$name,lapply(values,function(x) x$value))) else list(known=FALSE))
      }
      stop('static expression')
    }
    index_static<-function(expr) {
      if(expr$kind=='number') return(list(known=TRUE,value=expr$value))
      if(expr$kind=='variable') return(list(known=FALSE))
      if(expr$kind=='unary') {child<-index_static(expr$value);return(if(child$known) list(known=TRUE,value=if(expr$op=='-') -child$value else child$value) else list(known=FALSE))}
      if(expr$kind=='binary' && expr$op %in% c('+','-','*')) {
        a<-index_static(expr$left);b<-index_static(expr$right)
        return(if(a$known && b$known) list(known=TRUE,value=if(expr$op=='*') multiply(a$value,b$value) else add(a$value,b$value,expr$op=='-')) else list(known=FALSE))
      }
      stop('exact subscript grammar')
    }
    discover<-function(expr) {
      constant_expr(expr)
      if(expr$kind=='variable') {
        if(expr$name %in% names(arrays)) {if(!identical(expr$name,parsing_alias)) stop('inactive current alias')} else add_name(expr$name)
      }
      if(expr$kind %in% c('array_get','array_sum')) {
        a<-arrays[[expr$name]];if(is.null(a)) stop('array declaration order')
        if(expr$kind=='array_get') {
          if(a$implicit || !is.null(parsing_alias)) stop('indexed/current mixing')
          index<-index_static(expr$index)
          if(index$known && (is.na(index$value) || index$value!=trunc(index$value) || index$value<a$lower || index$value>=a$lower+length(a$names))) stop('static index')
          discover(expr$index)
        }
      }
      if(expr$kind=='binary') {discover(expr$left);discover(expr$right)}
      if(expr$kind=='unary') discover(expr$value)
      if(expr$kind=='call') for(arg in expr$args) discover(arg)
    }
    parse_condition<-function(text) {
      relation<-capture('(.+?)\\s*(>=|<=|\\^=|~=|<>|>|<|=|\\b(?:eq|ne|lt|le|gt|ge)\\b)\\s*(.+)',text)
      left<-parse_expr(if(is.null(relation)) text else relation[1]);discover(left)
      right<-if(is.null(relation)) NULL else parse_expr(relation[3]);if(!is.null(right)) discover(right)
      list(op=if(is.null(relation)) 'truth' else relation[2],left=left,right=right)
    }
    parse_op<-function(text,nested=FALSE,conditional=FALSE) {
      if(grepl('^array ',text)) {
        if(nested || conditional) stop('nested ARRAY')
        m<-capture('array\\s+([a-z_]\\w*)\\s*(?:\\{([^}]+)\\}|\\[([^]]+)\\]|\\(([^)]+)\\))?\\s*(.*)',text)
        if(is.null(m) || !ordinary(m[1]) || m[1] %in% c(names(arrays),names(schema),'_all_','_blankpage_','_character_','_error_','_file_','_infile_','_n_','_numeric_','_ods_','_page_','_temporary_','arcos','array','arsin','atan','band','blshift','bnot','bor','brshift','bxor','catx','constant','cos','count','data','dif','dif1','dif10','dif100','dif11','dif12','dif13','dif14','dif15','dif16','dif17','dif18','dif19','dif2','dif20','dif21','dif22','dif23','dif24','dif25','dif26','dif27','dif28','dif29','dif3','dif30','dif31','dif32','dif33','dif34','dif35','dif36','dif37','dif38','dif39','dif4','dif40','dif41','dif42','dif43','dif44','dif45','dif46','dif47','dif48','dif49','dif5','dif50','dif51','dif52','dif53','dif54','dif55','dif56','dif57','dif58','dif59','dif6','dif60','dif61','dif62','dif63','dif64','dif65','dif66','dif67','dif68','dif69','dif7','dif70','dif71','dif72','dif73','dif74','dif75','dif76','dif77','dif78','dif79','dif8','dif80','dif81','dif82','dif83','dif84','dif85','dif86','dif87','dif88','dif89','dif9','dif90','dif91','dif92','dif93','dif94','dif95','dif96','dif97','dif98','dif99','do','else','end','if','input','int','lag','lag1','lag10','lag100','lag11','lag12','lag13','lag14','lag15','lag16','lag17','lag18','lag19','lag2','lag20','lag21','lag22','lag23','lag24','lag25','lag26','lag27','lag28','lag29','lag3','lag30','lag31','lag32','lag33','lag34','lag35','lag36','lag37','lag38','lag39','lag4','lag40','lag41','lag42','lag43','lag44','lag45','lag46','lag47','lag48','lag49','lag5','lag50','lag51','lag52','lag53','lag54','lag55','lag56','lag57','lag58','lag59','lag6','lag60','lag61','lag62','lag63','lag64','lag65','lag66','lag67','lag68','lag69','lag7','lag70','lag71','lag72','lag73','lag74','lag75','lag76','lag77','lag78','lag79','lag8','lag80','lag81','lag82','lag83','lag84','lag85','lag86','lag87','lag88','lag89','lag9','lag90','lag91','lag92','lag93','lag94','lag95','lag96','lag97','lag98','lag99','length','lengthc','lengthn','max','mdy','merge','min','mod','output','put','quit','retain','reverse','round','run','set','sin','strip','substr','sum','tan','trim','weekday','where')) stop('ARRAY declaration')
        extent<-m[2:4];extent<-extent[nzchar(extent)];implicit<-!length(extent)
        members<-if(nzchar(m[5])) expand(m[5],1024L) else character()
        lo<-1L
        if(length(extent) && extent!='*') {
          bounds<-as.numeric(strsplit(extent,':',fixed=TRUE)[[1]])
          if(any(!is.finite(bounds)) || any(bounds!=trunc(bounds))) stop('ARRAY bounds')
          lo<-if(length(bounds)==2) bounds[1] else 1
          size<-if(length(bounds)==2) bounds[2]-bounds[1]+1 else bounds[1]
          if(!length(members) && size>=1 && size<=1024) members<-paste0(m[1],seq_len(size))
          if(length(members)!=size) stop('ARRAY extent')
        }
        if(!length(members) || length(members)>1024 || sum(vapply(arrays,function(a) length(a$names),0L))+length(members)>1024 ||
           lo < -2147483647 || lo+length(members)-1>2147483647 || any(members %in% names(arrays)) || m[1] %in% members) stop('ARRAY shape')
        arrays[[m[1]]]<<-list(names=members,lower=lo,implicit=implicit)
        for(n in members) add_name(n)
        return(list(kind='declare'))
      }
      if(grepl('^input ',text)) {
        if(nested || conditional || seen_executable || !is.null(inline_names) || length(input_names)) stop('INPUT position')
        names<-strsplit(sub('^input +','',text),' +')[[1]]
        if(!length(names) || length(names)>32 || anyDuplicated(names) || any(!vapply(names,ordinary,FALSE))) stop('INPUT names')
        inline_names<<-names;for(n in names) add_name(n);return(list(kind='declare'))
      }
      if(text %in% c('cards','datalines')) {
        if(nested || conditional || is.null(inline_names)) stop('inline source')
        decoded<-read_records(parsed$records[[as.character(at-1L)]],length(inline_names))
        input<<-lapply(decoded,function(row) setNames(as.list(row),inline_names));return(list(kind='declare'))
      }
      if(grepl('^set ',text)) {
        if(nested || conditional || seen_executable || !is.null(inline_names) || length(input_names)) stop('SET position')
        source<-dataset(text,'set');table<-tables[[source$name]];if(is.null(table)) stop('SET absent')
        input_names<<-choose(names(table$schema),source$projection)
        for(n in input_names) {
          if(!ordinary(n) || !(table$schema[[n]]$type %in% c('number','typed-number'))) stop('numeric SET')
          members<-unlist(lapply(arrays,function(a) a$names),use.names=FALSE)
          if(n %in% members) schema[[n]]<<-table$schema[[n]] else {
            add_name(n,table$schema[[n]])
            if(!(table$schema[[n]]$format %in% c('-','')) && schema[[n]]$format %in% c('-','')) {spec<-schema[[n]];spec$type<-'typed-number';spec$format<-table$schema[[n]]$format;schema[[n]]<<-spec}
          }
        }
        input<<-lapply(table$rows,function(row) lapply(row[input_names],numeric_operand))
        source_metadata<<-table[c('encoding','label')];return(list(kind='declare'))
      }
      if(grepl('^(keep|drop) ',text)) {
        if(nested || conditional || !is.null(outp)) stop('projection context')
        outp<<-selection(text);return(list(kind='declare'))
      }
      retain<-capture('retain\\s+([a-z_]\\w*)\\s+(.+)',text)
      if(!is.null(retain)) {
        if(nested || conditional || !ordinary(retain[1])) stop('RETAIN position');add_name(retain[1]);parsed_initial<-parse_expr(retain[2]);if(!(parsed_initial$kind=='number' || parsed_initial$kind=='unary' && parsed_initial$value$kind=='number')) stop('RETAIN literal');initial<-constant_expr(parsed_initial);if(!initial$known) stop('RETAIN literal')
        retained[[retain[1]]]<<-initial$value;return(list(kind='declare'))
      }
      seen_executable<<-TRUE
      over<-capture('do\\s+over\\s+([a-z_]\\w*)',text)
      conditional_loop<-capture('do\\s+(while|until)\\s*\\((.*)\\)',text)
      loop<-capture('do\\s+([a-z_]\\w*)\\s*=\\s*(.+?)\\s+to\\s+(.+?)(?:\\s+by\\s+(.+))?',text)
      if(!is.null(over) || !is.null(conditional_loop) || !is.null(loop)) {
        if(conditional) stop('conditional loop')
        if(nested && (is.null(loop) || any(parsing_loop!='loop'))) stop('loop nesting')
        if(!is.null(over)) {
          if(is.null(arrays[[over]]) || !arrays[[over]]$implicit || '_i_' %in% names(schema)) stop('implicit loop')
          over_seen<<-TRUE
          previous<-parsing_alias;parsing_alias<<-over;parsing_loop<<-c(parsing_loop,'over');body<-parse_body(TRUE)
          parsing_alias<<-previous;parsing_loop<<-head(parsing_loop,-1);return(list(kind='over',name=over,body=body))
        }
        if(!is.null(conditional_loop)) {
          condition<-parse_condition(conditional_loop[2]);parsing_loop<<-c(parsing_loop,conditional_loop[1]);body<-parse_body(TRUE);parsing_loop<<-head(parsing_loop,-1)
          return(c(list(kind=conditional_loop[1],body=body),condition))
        }
        if(loop[1] %in% c(names(arrays),unlist(lapply(arrays,function(a) a$names),use.names=FALSE),active_indices)) stop('counted index collision')
        add_name(loop[1]);controls<-lapply(c(loop[2],loop[3],if(nzchar(loop[4])) loop[4] else '1'),parse_expr)
        control_check<-function(expr) {
          if(expr$kind=='number') {x<-expr$value;if(is.na(x) || x!=trunc(x) || abs(x)>limit) stop('integer control');return()}
          if(expr$kind=='variable') {if(expr$name==loop[1] || expr$name %in% names(arrays)) stop('control self/array reference');add_name(expr$name);return()}
          if(expr$kind=='unary') {control_check(expr$value);return()}
          if(expr$kind!='binary' || !(expr$op %in% c('+','-'))) stop('exact control grammar')
          control_check(expr$left);control_check(expr$right)
        }
        for(control in controls) control_check(control)
        constants<-lapply(controls,index_static)
        if(all(vapply(constants,function(c) c$known,FALSE))) {
          values<-vapply(constants,function(c) c$value,0.0);if(values[3]==0) stop('zero BY')
          if(max(0,floor((values[2]-values[1])/values[3])+1)>10000) stop('counted budget')
        }
        if(length(parsing_loop)>=8) stop('counted depth')
        parsing_loop<<-c(parsing_loop,'loop');active_indices<<-c(active_indices,loop[1]);body<-parse_body(TRUE);parsing_loop<<-head(parsing_loop,-1);active_indices<<-head(active_indices,-1)
        return(list(kind='loop',name=loop[1],controls=controls,body=body))
      }
      condition<-capture('if\\s+(.+?)\\s+then\\s+(.+)',text);subset<-capture('if\\s+(.+)',text)
      if(!is.null(condition) || !is.null(subset)) {
        if(is.null(condition) && nested) stop('nested subsetting IF')
        c<-if(!is.null(condition)) condition else subset;predicate<-parse_condition(c[1])
        return(c(list(kind=if(is.null(condition)) 'subset' else 'if',body=if(is.null(condition)) list() else list(parse_op(c[2],nested,TRUE))),predicate))
      }
      put<-capture('put\\s+([a-z_]\\w*(?:\\s+[a-z_]\\w*)*)',text)
      if(!is.null(put)) {names<-strsplit(put,'\\s+',perl=TRUE)[[1]];for(n in names) add_name(n);return(list(kind='put',names=names))}
      if(text=='output') {explicit<<-TRUE;return(list(kind='output'))}
      indexed<-capture('([a-z_]\\w*)\\s*(?:\\{([^}]+)\\}|\\[([^]]+)\\])\\s*=\\s*(.+)',text)
      if(!is.null(indexed)) {
        index<-parse_expr(if(nzchar(indexed[2])) indexed[2] else indexed[3]);value<-parse_expr(indexed[4]);discover(list(kind='array_get',name=indexed[1],index=index));discover(value)
        return(list(kind='indexed_set',name=indexed[1],index=index,value=value))
      }
      assignment<-capture('([a-z_]\\w*)\\s*=\\s*(.+)',text);summation<-capture('([a-z_]\\w*)\\s*\\+\\s*(.+)',text)
      if(!is.null(assignment) || !is.null(summation)) {
        m<-if(!is.null(assignment)) assignment else summation
        if(m[1] %in% names(arrays)) {
          if(!identical(m[1],parsing_alias) || is.null(assignment)) stop('current assignment')
          value<-parse_expr(m[2]);discover(value);return(list(kind='current_set',name=m[1],value=value))
        }
        if(!ordinary(m[1]) || m[1] %in% active_indices || (is.null(assignment) && !is.null(parsing_alias))) stop('ordinary assignment target')
        add_name(m[1]);value<-parse_expr(m[2]);discover(value)
        if(is.null(assignment) && is.null(retained[[m[1]]])) retained[[m[1]]]<<-0
        return(list(kind=if(is.null(assignment)) 'sum' else 'assign',name=m[1],value=value))
      }
      stop(paste('unsupported statement',text))
    }
    parse_body<-function(nested=FALSE) {
      body<-list()
      repeat {
        if(at>length(statements)) stop('missing terminator')
        text<-tolower(statements[at]);at<<-at+1L
        if(text=='end') {if(!nested) stop('unexpected END');return(body)}
        if(text=='run') {if(nested) stop('RUN in loop');return(body)}
        if(grepl('^else ',text)) {
          if(!length(body) || tail(body,1)[[1]]$kind!='if' || !is.null(tail(body,1)[[1]]$otherwise)) stop('ELSE adjacency')
          body[[length(body)]]$otherwise<-list(parse_op(sub('^else +','',text),nested,TRUE))
        } else body[[length(body)+1L]]<-parse_op(text,nested)
      }
    }
    body<-parse_body();chosen<-choose(names(schema),outp);output<-list();trips<-0L;iteration<-0L;row<-list();current<-list();counted_spent<-0L
    members<-unlist(lapply(arrays,function(a) a$names),use.names=FALSE)
    if(length(intersect(names(retained),members)) || length(intersect(names(arrays),names(schema)))) stop('array state collision')
    check_put<-function(body) for(op in body) {if(op$kind=='put') for(n in op$names) if(!(schema[[n]]$format %in% c('-',''))) stop('formatted PUT');if(!is.null(op$body)) check_put(op$body);if(!is.null(op$otherwise)) check_put(op$otherwise)}
    check_put(body)
    index_eval<-function(expr) {
      if(expr$kind=='number') return(expr$value)
      if(expr$kind=='variable') return(if(expr$name=='_n_') iteration else row[[expr$name]])
      if(expr$kind=='unary') return(if(expr$op=='-') -index_eval(expr$value) else index_eval(expr$value))
      if(expr$kind=='binary' && expr$op %in% c('+','-','*')) {
        a<-index_eval(expr$left);b<-index_eval(expr$right)
        return(if(expr$op=='*') multiply(a,b) else add(a,b,expr$op=='-'))
      }
      stop('exact dynamic subscript')
    }
    offset<-function(name,expr) {
      a<-arrays[[name]];i<-index_eval(expr)
      if(is.na(i) || !is.finite(i) || i!=trunc(i) || i<a$lower || i>=a$lower+length(a$names)) stop('dynamic subscript')
      as.integer(i-a$lower+1)
    }
    evaluate<-function(expr) {
      if(expr$kind %in% c('number','string')) return(expr$value)
      if(expr$kind=='variable') {
        if(expr$name %in% names(arrays)) return(numeric_operand(row[[arrays[[expr$name]]$names[current[[expr$name]]]]]))
        return(numeric_operand(if(expr$name=='_n_') iteration else row[[expr$name]]))
      }
      if(expr$kind=='unary') return(numeric_operand(if(expr$op=='-') -evaluate(expr$value) else evaluate(expr$value)))
      if(expr$kind=='binary') return(arithmetic(expr$op,evaluate(expr$left),evaluate(expr$right)))
      if(expr$kind=='call') return(call(expr$name,lapply(expr$args,evaluate)))
      if(expr$kind=='array_get') return(numeric_operand(row[[arrays[[expr$name]]$names[offset(expr$name,expr$index)]]]))
      if(expr$kind=='array_sum') {
        values<-lapply(row[arrays[[expr$name]]$names],numeric_operand);total<-NA_real_
        for(value in values) if(!is.na(value)) total<-if(is.na(total)) value else arithmetic('+',total,value)
        return(total)
      }
      stop('unsupported expression')
    }
    test<-function(op) {
      a<-evaluate(op$left);if(op$op=='truth') return(!is.na(a) && a!=0)
      b<-evaluate(op$right)
      if(is.na(a) || is.na(b)) {if(is.na(a) && is.na(b)) {a<-0;b<-0} else {a<-if(is.na(a)) -Inf else a;b<-if(is.na(b)) -Inf else b}}
      switch(op$op,'>'=a>b,gt=a>b,'<'=a<b,lt=a<b,'>='=a>=b,ge=a>=b,'<='=a<=b,le=a<=b,'='=a==b,eq=a==b,ne=a!=b,'^='=a!=b,'~='=a!=b,'<>'=a!=b)
    }
    perform<-function(body) {
      for(op in body) {
        if(op$kind=='declare') next
        if(op$kind=='assign') row[[op$name]]<<-evaluate(op$value)
        else if(op$kind=='indexed_set') row[[arrays[[op$name]]$names[offset(op$name,op$index)]]]<<-evaluate(op$value)
        else if(op$kind=='current_set') row[[arrays[[op$name]]$names[current[[op$name]]]]]<<-evaluate(op$value)
        else if(op$kind=='sum') {value<-evaluate(op$value);old<-row[[op$name]];row[[op$name]]<<-arithmetic('+',if(is.na(old)) 0 else old,if(is.na(value)) 0 else value)}
        else if(op$kind=='output') output[[length(output)+1L]]<<-row[chosen]
        else if(op$kind=='put') logs<<-c(logs,record(row[op$names]))
        else if(op$kind=='subset') {if(!test(op)) return(FALSE)}
        else if(op$kind=='if') {if(test(op)) {if(!perform(op$body)) return(FALSE)} else if(!is.null(op$otherwise) && !perform(op$otherwise)) return(FALSE)}
        else if(op$kind=='loop') {
          controls<-vapply(op$controls,index_eval,0.0)
          if(any(is.na(controls)) || any(!is.finite(controls)) || any(controls!=trunc(controls)) || any(abs(controls)>limit) || controls[3]==0) stop('dynamic control')
          count<-max(0,floor((controls[2]-controls[1])/controls[3])+1)
          counted_spent<<-counted_spent+count;if(counted_spent>10000) stop('counted row budget')
          row[[op$name]]<<-controls[1]
          if(count) for(k in seq_len(count)) {trips<<-trips+1L;perform(op$body);row[[op$name]]<<-row[[op$name]]+controls[3]}
        } else if(op$kind=='over') {
          for(k in seq_along(arrays[[op$name]]$names)) {current[[op$name]]<<-k;trips<<-trips+1L;perform(op$body)}
          current[[op$name]]<<-NULL
        } else if(op$kind %in% c('while','until')) {
          local_trips<-0L
          repeat {
            if(op$kind=='while' && !test(op)) break
            local_trips<-local_trips+1L;if(local_trips>10000) stop('conditional loop budget')
            trips<<-trips+1L;perform(op$body)
            if(op$kind=='until' && test(op)) break
          }
        } else stop('unsupported execution')
      }
      TRUE
    }
    for(inrow in input) {
      iteration<-iteration+1L;counted_spent<-0L
      row<-setNames(as.list(rep(NA_real_,length(schema))),names(schema));row[names(retained)]<-retained;row[names(inrow)]<-inrow
      completed<-perform(body);retained<-row[unique(c(input_names,names(retained)))]
      if(completed && !explicit) output[[length(output)+1L]]<-row[chosen]
    }
    table<-list(schema=schema[chosen],rows=output,encoding=source_metadata$encoding,label=source_metadata$label)
    if(name!='_null_') tables[[name]]<-table
    accounts[[length(accounts)+1L]]<-list(name=name,iterations=length(input),trips=trips)
  }
  for(n in names(tables)) {
    table<-tables[[n]];cat('TABLE:',n,'\n','META:',table$encoding,'|',table$label,'\n',sep='')
    for(nm in names(table$schema)) {spec<-table$schema[[nm]];cat('COLUMN:',paste(c(nm,spec$type,spec$length,spec$label,spec$format),collapse='|'),'\n',sep='')}
    for(row in table$rows) cat('ROW:',encode_row(row[names(table$schema)]),'\n',sep='')
  }
  for(account in accounts) cat('ACCOUNT:',account$name,',',account$iterations,',',account$trips,'\n',sep='')
  for(log in logs) cat('LOG:',hex(log),'\n',sep='')
}
args<-commandArgs(trailingOnly=TRUE)
if(length(args)==3L && args[1]=='program') program(args[2],args[3]) else if(length(args)==2L && args[1]=='batch') {
  cases<-read.csv(file.path(args[2],'cases.csv'),colClasses='character')
  for(i in seq_len(nrow(cases))) {
    cat('CASE:',i-1L,'\n',sep='')
    passed<-tryCatch({program(file.path(args[2],cases$source[i]),file.path(args[2],cases$catalog[i]));TRUE},error=function(e) {cat('REASON:',conditionMessage(e),'\n',sep='');FALSE})
    cat('ANSWER:',if(passed) 'OK' else 'REFUSE','\n',sep='')
  }
} else stop('program path catalog-folder or batch folder required')
